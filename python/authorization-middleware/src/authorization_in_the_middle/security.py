"""``with_security`` — JWT authn + Cedar authz for Neosofia REST services.

Reading order (matches the README glossary):

1. **Route inference** — ``infer_crud_action``, ``infer_resource``, ``infer_id_arg``
2. **Catalog vs member** — collection/list/create → ``*Catalog``; path id → ``Member``
3. **Resource UID + entity records** — ``resource_fn``, ``entities_fn`` for the evaluator
4. **``with_security``** — pass overrides; infer anything omitted at request time

Terms: **Action**, **Resource**, **Member** (one record, path id), **Catalog** (collection /
fixed catalog id), **Entity** (principal + resource records for Cedar).
"""
from __future__ import annotations

import importlib
import re
from functools import wraps
from typing import Any, Callable

import inflect
from authentication_in_the_middle.decorators import with_authentication
from authorization_in_the_middle.decorators import with_authorization
from logenvelope.flask import cedar_principal_log_fields, log_request_event
from authorization_in_the_middle.entities import entity_uid
from authorization_in_the_middle.logging_context import set_authz_outcome_log_extra
from flask import current_app, request

_CATALOG_COLLECTION_VERBS = frozenset({"list", "create"})


class EvaluatorProxy:
    def is_authorized(self, *args: Any, **kwargs: Any) -> bool:
        return current_app.extensions["cedar_evaluator"].is_authorized(*args, **kwargs)


evaluator_proxy = EvaluatorProxy()


def request_context() -> dict[str, Any]:
    return {"http_method": request.method, "route": request.url_rule.rule if request.url_rule else ""}


def request_view_arg(arg_name: str) -> str:
    return request.view_args[arg_name] if request.view_args and arg_name in request.view_args else ""


# --- Route inference (CRUD action + resource name from Flask rule) ---

_ROUTE_PREFIX_SEGMENTS = frozenset({"api"})
_VERSION_SEGMENT = re.compile(r"^v\d+$", re.IGNORECASE)
_INFLECT = inflect.engine()


def _singularize(segment: str) -> str:
    singular = _INFLECT.singular_noun(segment)
    return singular if singular else segment


def _route_noun_segments(rule: str) -> list[str]:
    segments = [s for s in rule.split("/") if s and not s.startswith("<")]
    return [
        s for s in segments
        if s not in _ROUTE_PREFIX_SEGMENTS and not _VERSION_SEGMENT.match(s)
    ]


def infer_resource() -> str:
    """Infer Cedar resource name from the first noun segment in the route rule."""
    rule = request.url_rule.rule if request.url_rule else request.path
    nouns = _route_noun_segments(rule)
    if not nouns:
        raise ValueError(f"cannot infer resource from route {rule}")
    return _singularize(nouns[0])


def infer_id_arg() -> str | None:
    """First ``<param>`` in the route rule (e.g. ``user_uuid``, ``slug``)."""
    rule = request.url_rule.rule if request.url_rule else ""
    params = re.findall(r"<(?:\w+:)?(\w+)>", rule)
    return params[0] if params else None


def infer_crud_action(resource: str | None = None, *, id_arg: str | None = None) -> str:
    """Infer Cedar CRUD **Action** from HTTP method and whether a **Member** id is in the path."""
    method = request.method.upper()
    view_args = request.view_args or {}
    resource_name = resource or infer_resource()
    member_arg = id_arg or infer_id_arg()
    member = member_arg if member_arg and member_arg in view_args else None
    if member is None:
        if method == "GET":
            return f'Action::"{resource_name}:list"'
        if method == "POST":
            return f'Action::"{resource_name}:create"'
        raise ValueError(f"cannot infer Cedar action for {method}")
    verb = {"GET": "read", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(method)
    if verb is None:
        raise ValueError(f"cannot infer Cedar action for {method}")
    return f'Action::"{resource_name}:{verb}"'


def _resolve_id_arg(id_arg: str | None, model_name: str) -> str:
    """Member path param: explicit ``id_arg`` → route rule → ``{model}_uuid`` fallback."""
    if id_arg:
        return id_arg
    from flask import has_request_context

    inferred = infer_id_arg() if has_request_context() else None
    if inferred:
        return inferred
    return f"{model_name}_uuid"


# --- Parse Action; map to Cedar Resource type (Member vs Catalog) ---

def _action_parts(action: str) -> tuple[str, str]:
    action_key = action[len('Action::"'):-1] if action.startswith('Action::"') else action
    model_name, verb = action_key.split(":", 1)
    return model_name.replace("-", "_").lower(), verb.lower()


def _pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _catalog_constant_name(model_name: str) -> str:
    if model_name.endswith("_catalog"):
        return f"{model_name.upper()}_ID"
    return f"{model_name.upper()}_CATALOG_ID"


def _is_catalog_collection(verb: str) -> bool:
    """``user:list`` / ``user:create`` — README collection verbs."""
    return verb in _CATALOG_COLLECTION_VERBS


def _is_catalog_singleton(model_name: str, verb: str) -> bool:
    """``role_catalog:read`` on a fixed catalog id."""
    return verb == "read" and model_name.endswith("_catalog")


def _uses_catalog_scope(model_name: str, verb: str, id_arg: str | None) -> bool:
    """True when the Cedar **Resource** is a **Catalog**, not a **Member**.

    - ``list`` / ``create`` → Catalog (e.g. ``GET /api/services`` → ``ServiceCatalog``)
    - ``audit:list`` (and similar) with no member id in the path → Catalog
      (e.g. ``GET /api/services/audits`` — ``audits`` is not an id)
    - Same action with a member id present → Member (e.g. ``GET .../<slug>/audits``)
    """
    if _is_catalog_collection(verb) or _is_catalog_singleton(model_name, verb):
        return True
    from flask import has_request_context

    if not has_request_context():
        return False
    member_arg = _resolve_id_arg(id_arg, model_name)
    view_args = request.view_args or {}
    return member_arg not in view_args and ":list" in verb


def _scope_resource_name(
    model_name: str,
    verb: str,
    resource_type: str | None,
    *,
    catalog: bool,
) -> str:
    """Cedar **Resource** type name: ``UserCatalog`` (Catalog) or ``User`` (Member)."""
    if catalog:
        catalog_verb = verb if _is_catalog_collection(verb) else "list"
        return resource_type or _catalog_resource_type(model_name, catalog_verb)
    return _item_resource_type(model_name, resource_type)


def _catalog_resource_type(model_name: str, verb: str) -> str:
    base = _pascal_case(model_name)
    if _is_catalog_collection(verb):
        return f"{_pascal_case(model_name.split('_')[0])}Catalog" if "_" not in model_name else base
    return base


def _item_resource_type(model_name: str, resource_type: str | None) -> str:
    if resource_type:
        return resource_type
    return _pascal_case(model_name)


def _resource_uid_from_view_arg(
    namespace: str,
    resource_name: str,
    id_arg: str,
) -> str:
    resource_id = request_view_arg(id_arg)
    return entity_uid(f"{namespace}::{resource_name}", resource_id)


def _resource_uid_for_catalog(namespace: str, resource_name: str, catalog_id: str) -> str:
    return entity_uid(f"{namespace}::{resource_name}", catalog_id)


def _catalog_id(model_name: str, verb: str, entities_mod: Any, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    if entities_mod is not None:
        const = _catalog_constant_name(model_name)
        if hasattr(entities_mod, const):
            return str(getattr(entities_mod, const))
    return f"{model_name.replace('_', '-')}-catalog"


# --- Service ``src.authorization.entities`` conventions ---

def _import_entities_module():
    try:
        return importlib.import_module("src.authorization.entities")
    except ImportError:
        return None


def _resolve_principal(entities_mod: Any) -> dict[str, Any]:
    if entities_mod is not None:
        if hasattr(entities_mod, "resolve_principal"):
            return entities_mod.resolve_principal()
        if hasattr(entities_mod, "load_principal_entity"):
            return entities_mod.load_principal_entity()
    raise ValueError(
        "src.authorization.entities must define resolve_principal() or load_principal_entity()"
    )


def _principal_uid(entities_mod: Any) -> str:
    entity = _resolve_principal(entities_mod)
    ref = entity["uid"]["__entity"]
    return entity_uid(ref["type"], ref["id"])


def _find_resource_builder(
    entities_mod: Any,
    model_mod: Any,
    model_name: str,
    builder_module_name: str,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    candidates: list[tuple[Any, str]] = []
    if entities_mod is not None:
        candidates.extend(
            (
                (entities_mod, f"build_{model_name}_resource_entity"),
                (entities_mod, f"build_{builder_module_name}_resource_entity"),
            )
        )
    if model_mod is not None:
        candidates.extend(
            (
                (model_mod, f"build_{builder_module_name}_entity"),
                (model_mod, f"build_{model_name}_entity"),
            )
        )
    for mod, attr in candidates:
        if mod is not None and hasattr(mod, attr):
            return getattr(mod, attr)
    raise AttributeError(
        f"No resource entity builder found for model '{model_name}' "
        f"(module '{builder_module_name}')"
    )


def _type_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _find_catalog_builder(entities_mod: Any, model_mod: Any, catalog_resource_type: str) -> Callable[[], dict[str, Any]]:
    snake = _type_to_snake(catalog_resource_type)
    for mod in (entities_mod, model_mod):
        if mod is None:
            continue
        for attr in (f"build_{snake}_entity",):
            if hasattr(mod, attr):
                fn = getattr(mod, attr)
                return lambda fn=fn: fn()
    raise AttributeError(f"No catalog builder found for '{catalog_resource_type}'")


# --- Build ``resource_fn`` + ``entities_fn`` (principal + resource **Entity** records) ---

def _rest_entities_for_item(
    service_model: str,
    builder_module_name: str,
    id_arg: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Principal + **Member** resource entity (id from path; no DB load unless ``resource_loader``)."""
    member_arg = _resolve_id_arg(id_arg, service_model)
    resource_id = request_view_arg(member_arg)
    try:
        model_mod = importlib.import_module(f"src.models.{builder_module_name}")
    except ImportError:
        model_mod = None
    build_resource_entity = _find_resource_builder(
        entities_mod,
        model_mod,
        service_model,
        builder_module_name,
    )
    loaded = resource_loader(resource_id) if resource_loader else None
    return [
        _resolve_principal(entities_mod),
        build_resource_entity(resource_id, loaded),
    ]


def _rest_entities_for_catalog(
    build_catalog_entity: Callable[[], dict[str, Any]],
    entities_mod: Any,
) -> list[dict[str, Any]]:
    """Principal + **Catalog** resource entity (fixed catalog id)."""
    return [
        _resolve_principal(entities_mod),
        build_catalog_entity(),
    ]


def _resource_uid_for_action(
    *,
    namespace: str,
    model_name: str,
    verb: str,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    entities_mod: Any,
) -> str:
    """Cedar **Resource** UID for one **Action** (Catalog constant or Member path id)."""
    catalog = _uses_catalog_scope(model_name, verb, id_arg)
    resource_name = _scope_resource_name(model_name, verb, resource_type, catalog=catalog)
    if catalog:
        catalog_verb = verb if _is_catalog_collection(verb) else "list"
        return _resource_uid_for_catalog(
            namespace,
            resource_name,
            _catalog_id(model_name, catalog_verb, entities_mod, catalog_id),
        )
    return _resource_uid_from_view_arg(
        namespace,
        resource_name,
        _resolve_id_arg(id_arg, model_name),
    )


def _entities_for_action(
    *,
    model_name: str,
    verb: str,
    builder_module_name: str,
    id_arg: str | None,
    resource_type: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """``[principal_entity, resource_entity]`` for one **Action**."""
    if _uses_catalog_scope(model_name, verb, id_arg):
        try:
            model_mod = importlib.import_module(f"src.models.{builder_module_name}")
        except ImportError:
            model_mod = None
        resource_name = _scope_resource_name(model_name, verb, resource_type, catalog=True)
        build_catalog = _find_catalog_builder(entities_mod, model_mod, resource_name)
        return _rest_entities_for_catalog(build_catalog, entities_mod)
    return _rest_entities_for_item(
        model_name,
        builder_module_name,
        id_arg,
        entities_mod,
        resource_loader,
    )


def _infer_rest_fns(
    action: str,
    *,
    resource_fn: Callable[[], str] | None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None,
    namespace: str | None,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    entity_module: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[Callable[[], str], Callable[[], list[dict[str, Any]]], str, str]:
    """Fill in omitted ``resource_fn`` / ``entities_fn`` for a resolved Cedar **Action**."""
    resource_fn_local = resource_fn
    entities_fn_local = entities_fn

    model_name, verb = _action_parts(action)
    builder_module_name = entity_module or model_name
    resolved_resource_name = _scope_resource_name(
        model_name,
        verb,
        resource_type,
        catalog=_is_catalog_collection(verb) or _is_catalog_singleton(model_name, verb),
    )

    inferred_namespace = namespace
    if inferred_namespace is None:
        if entities_mod is not None and hasattr(entities_mod, "NAMESPACE"):
            inferred_namespace = entities_mod.NAMESPACE
        else:
            try:
                model_mod = importlib.import_module(f"src.models.{builder_module_name}")
                inferred_namespace = getattr(model_mod, "NAMESPACE")
            except (ImportError, AttributeError) as exc:
                raise ValueError(
                    f"Could not infer Cedar namespace for '{model_name}'. "
                    f"Set namespace= or add NAMESPACE to src.authorization.entities. Error: {exc}"
                ) from exc

    if resource_fn_local is None:
        resource_fn_local = lambda ns=inferred_namespace, mn=model_name, v=verb, explicit=id_arg, rt=resource_type, cid=catalog_id, em=entities_mod: (
            _resource_uid_for_action(
                namespace=ns,
                model_name=mn,
                verb=v,
                id_arg=explicit,
                resource_type=rt,
                catalog_id=cid,
                entities_mod=em,
            )
        )

    if entities_fn_local is None:
        entities_fn_local = lambda mn=model_name, v=verb, bm=builder_module_name, explicit=id_arg, rt=resource_type, em=entities_mod, rl=resource_loader: (
            _entities_for_action(
                model_name=mn,
                verb=v,
                builder_module_name=bm,
                id_arg=explicit,
                resource_type=rt,
                entities_mod=em,
                resource_loader=rl,
            )
        )

    return resource_fn_local, entities_fn_local, resolved_resource_name, id_arg or f"{model_name}_uuid"


def _infer_kwargs(
    *,
    resource_fn: Callable[[], str] | None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None,
    namespace: str | None,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    entity_module: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Shared kwargs for ``_infer_rest_fns`` (decorator + logging)."""
    return {
        "resource_fn": resource_fn,
        "entities_fn": entities_fn,
        "namespace": namespace,
        "id_arg": id_arg,
        "resource_type": resource_type,
        "catalog_id": catalog_id,
        "entity_module": entity_module,
        "entities_mod": entities_mod,
        "resource_loader": resource_loader,
    }


# --- Public decorator ---

def with_security(
    action: str | None = None,
    resource: str | None = None,
    resource_fn: Callable[[], str] | None = None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None = None,
    namespace: str | None = None,
    build_resource_entity: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
    id_arg: str | None = None,
    rate_limit: str = "60 per minute",
    enforce_active_actor: bool = True,
    resource_type: str | None = None,
    catalog_id: str | None = None,
    entity_module: str | None = None,
) -> Callable:
    """
    JWT authentication + Cedar authorization for a Flask route.

    Omit ``action`` to infer CRUD **Action** from method + path. Pass any parameter
    explicitly to override; omitted ``resource_fn`` and ``entities_fn`` are inferred
    at request time (Catalog vs Member per README).

    ``src.authorization.entities`` must provide ``NAMESPACE``, ``resolve_principal()``,
    and ``build_{model}_resource_entity`` / ``build_{catalog}_entity`` as needed.
    """
    if action is not None and resource is not None:
        raise TypeError("with_security: pass action or resource, not both")

    def decorator(f: Callable) -> Callable:
        entities_mod = _import_entities_module()
        crud_resource = resource
        use_crud_inference = action is None
        infer_kw = _infer_kwargs(
            resource_fn=resource_fn,
            entities_fn=entities_fn,
            namespace=namespace,
            id_arg=id_arg,
            resource_type=resource_type,
            catalog_id=catalog_id,
            entity_module=entity_module,
            entities_mod=entities_mod,
            resource_loader=resource_loader,
        )

        if use_crud_inference:
            def resolved_action() -> str:
                return infer_crud_action(crud_resource, id_arg=id_arg)

            def resolved_resource_fn() -> str:
                act = resolved_action()
                rf, _, _, _ = _infer_rest_fns(act, **infer_kw)
                return rf()

            def resolved_entities_fn() -> list[dict[str, Any]]:
                act = resolved_action()
                _, ef, _, _ = _infer_rest_fns(act, **infer_kw)
                return ef()

            action_for_authz: str | Callable[[], str] = resolved_action
            resource_fn_local = resolved_resource_fn
            entities_fn_local = resolved_entities_fn
            resolved_resource_name = ""
            target_id_arg = id_arg or ""
        else:
            action_for_authz = action  # type: ignore[assignment]
            if callable(action):
                if resource_fn is None or entities_fn is None:
                    raise TypeError("callable action requires resource_fn and entities_fn")
                resource_fn_local = resource_fn
                entities_fn_local = entities_fn
                resolved_resource_name = ""
                target_id_arg = id_arg or ""
            else:
                resource_fn_local, entities_fn_local, resolved_resource_name, target_id_arg = _infer_rest_fns(
                    action,  # type: ignore[arg-type]
                    **infer_kw,
                )

        authz_decorator = with_authorization(
            evaluator_proxy,
            principal_fn=lambda em=entities_mod: _principal_uid(em),
            action=action_for_authz,
            resource_fn=resource_fn_local,
            entities_fn=entities_fn_local,
            context_fn=request_context,
            log_event=log_request_event,
        )

        authn_decorator = with_authentication(enforce_active_actor=enforce_active_actor)

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                principal_entity = _resolve_principal(entities_mod)
                principal_fields = cedar_principal_log_fields(principal_entity)
            except Exception:
                principal_fields = {"principal": "unknown"}

            log_resource_name = resolved_resource_name
            log_target_id_arg = target_id_arg
            if use_crud_inference:
                act = infer_crud_action(crud_resource, id_arg=id_arg)
                _, _, log_resource_name, log_target_id_arg = _infer_rest_fns(act, **infer_kw)

            set_authz_outcome_log_extra(
                rate_limit=rate_limit,
                resource_name=log_resource_name,
                resource_id=catalog_id or kwargs.get(log_target_id_arg),
                tenant_uuid=principal_fields.get("tenant_uuid"),
                tenant_type=principal_fields.get("tenant_type"),
            )
            return authz_decorator(f)(*args, **kwargs)

        final_handler = authn_decorator(wrapper)

        try:
            from src.bootstrap.extensions import limiter
            final_handler = limiter.limit(rate_limit)(final_handler)
        except ImportError:
            pass

        return final_handler

    return decorator
