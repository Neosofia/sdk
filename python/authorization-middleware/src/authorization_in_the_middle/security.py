import importlib
import re
from functools import wraps
from typing import Any, Callable

from authentication_in_the_middle.decorators import with_authentication
from authorization_in_the_middle.decorators import with_authorization
from logenvelope.flask import cedar_principal_log_fields, log_request_event
from authorization_in_the_middle.entities import entity_uid
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
    return verb in _CATALOG_COLLECTION_VERBS


def _is_catalog_singleton(model_name: str, verb: str) -> bool:
    return verb == "read" and model_name.endswith("_catalog")


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


def _import_entities_module():
    try:
        return importlib.import_module("src.authorization.entities")
    except ImportError:
        return None


def _catalog_id(model_name: str, verb: str, entities_mod: Any, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    if entities_mod is not None:
        const = _catalog_constant_name(model_name)
        if hasattr(entities_mod, const):
            return str(getattr(entities_mod, const))
    return f"{model_name.replace('_', '-')}-catalog"


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


def _rest_entities_for_item(
    service_model: str,
    builder_module_name: str,
    id_arg: str,
    entities_mod: Any,
) -> list[dict[str, Any]]:
    resource_id = request_view_arg(id_arg)
    service_mod = importlib.import_module(f"src.services.{service_model}_service")
    loader = getattr(service_mod, f"get_{service_model}_or_404")
    resource = loader(resource_id)
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
    return [
        _resolve_principal(entities_mod),
        build_resource_entity(resource_id, resource),
    ]


def _rest_entities_for_catalog(
    build_catalog_entity: Callable[[], dict[str, Any]],
    entities_mod: Any,
) -> list[dict[str, Any]]:
    return [
        _resolve_principal(entities_mod),
        build_catalog_entity(),
    ]


def with_security(
    action: str,
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
    rest: bool = True,
) -> Callable:
    """
    Unified security decorator for Neosofia REST services.

    When ``rest=True`` (default), infers ``resource_fn`` and ``entities_fn`` from the action
    and Flask path so routes need only ``action`` and ``rate_limit``:

    - ``user:read`` + ``/<user_id>`` → ``users::User`` (resource UID from path; row loaded for entities)
    - ``user:list`` / ``user:create`` → ``users::UserCatalog`` (catalog id from ``USER_CATALOG_ID``)
    - ``role_catalog:read`` → ``users::RoleCatalog`` singleton

    Override ``resource_fn`` / ``entities_fn`` only when inference does not fit.

    ``src.authorization.entities`` must provide:
    - ``NAMESPACE``, optional ``{MODEL}_CATALOG_ID``
    - ``resolve_principal()`` (or ``load_principal_entity()``) for the Cedar principal
    - ``build_{model}_resource_entity``, ``build_{catalog}_entity`` when using REST inference
    """
    def decorator(f: Callable) -> Callable:
        resource_fn_local = resource_fn
        entities_fn_local = entities_fn

        model_name, verb = _action_parts(action)
        target_id_arg = id_arg or f"{model_name}_id"
        builder_module_name = entity_module or model_name
        entities_mod = _import_entities_module()
        is_catalog_collection = _is_catalog_collection(verb)
        is_catalog_singleton = _is_catalog_singleton(model_name, verb)

        if is_catalog_collection or is_catalog_singleton:
            resolved_resource_name = resource_type or _catalog_resource_type(model_name, verb)
        else:
            resolved_resource_name = _item_resource_type(model_name, resource_type)

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

        if rest and (resource_fn_local is None or entities_fn_local is None):
            inferred_loader = resource_loader
            inferred_builder = build_resource_entity
            model_mod = None

            if resource_fn_local is None:
                if is_catalog_collection or is_catalog_singleton:
                    catalog_key = _catalog_id(model_name, verb, entities_mod, catalog_id)
                    resource_fn_local = lambda cid=catalog_key, rn=resolved_resource_name, ns=inferred_namespace: (
                        _resource_uid_for_catalog(ns, rn, cid)
                    )
                else:
                    resource_fn_local = lambda ns=inferred_namespace, rn=resolved_resource_name, arg=target_id_arg: (
                        _resource_uid_from_view_arg(ns, rn, arg)
                    )

            if entities_fn_local is None:
                if is_catalog_collection or is_catalog_singleton:
                    if model_mod is None:
                        try:
                            model_mod = importlib.import_module(f"src.models.{builder_module_name}")
                        except ImportError:
                            model_mod = None
                    build_catalog = _find_catalog_builder(
                        entities_mod,
                        model_mod,
                        resolved_resource_name,
                    )
                    entities_fn_local = lambda bc=build_catalog, em=entities_mod: (
                        _rest_entities_for_catalog(bc, em)
                    )
                else:
                    entities_fn_local = lambda sm=model_name, bm=builder_module_name, arg=target_id_arg, em=entities_mod: (
                        _rest_entities_for_item(sm, bm, arg, em)
                    )

        elif resource_fn_local is None or entities_fn_local is None:
            if resource_fn_local is None and catalog_id is not None and inferred_namespace:
                resource_fn_local = lambda: _resource_uid_for_catalog(
                    inferred_namespace,
                    resolved_resource_name,
                    catalog_id,
                )

        authz_decorator = with_authorization(
            evaluator_proxy,
            principal_fn=lambda em=entities_mod: _principal_uid(em),
            action=action,
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

            log_request_event(
                "security_evaluation_started",
                route=f.__name__,
                action=action,
                resource_name=resolved_resource_name,
                resource_id=catalog_id or kwargs.get(target_id_arg),
                rate_limit=rate_limit,
                **principal_fields,
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
