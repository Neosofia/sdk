"""``with_security`` — JWT authn + Cedar authz for Neosofia REST services.

Reading order (matches the README glossary):

1. **Route inference** — ``route_inference`` — ``infer_crud_action``, ``infer_resource``, ``infer_id_arg``
2. **Catalog vs member** — ``action_scope`` — collection/list/create → ``*Catalog``; path id → ``Member``
3. **Resource UID + entity records** — ``rest_entities`` — ``resource_fn``, ``entities_fn`` for the evaluator
4. **``with_security``** — pass overrides; infer anything omitted at request time

Terms: **Action**, **Resource**, **Member** (one record, path id), **Catalog** (collection /
fixed catalog id), **Entity** (principal + resource records for Cedar).
"""
from __future__ import annotations

import importlib
from functools import wraps
from typing import Any, Callable

from authentication_in_the_middle.decorators import with_authentication
from authorization_in_the_middle.action_scope import (
    _action_parts,
    _catalog_constant_name,
    _catalog_resource_type,
    _is_catalog_collection,
    _is_catalog_singleton,
    _resolve_id_arg,
    _resource_uid_for_action,
    _type_to_snake,
    _uses_catalog_scope,
)
from authorization_in_the_middle.decorators import with_authorization
from authorization_in_the_middle.flask_request import request_context, request_view_arg
from authorization_in_the_middle.logging_context import set_authz_outcome_log_extra
from authorization_in_the_middle.openapi_request import parse_flask_request_body
from authorization_in_the_middle.rest_entities import (
    _entities_for_write_member,
    _infer_kwargs,
    _infer_rest_fns,
    _resource_uid_for_write_member,
    _resource_uid_from_entity,
)
from authorization_in_the_middle.route_inference import (
    infer_crud_action,
    infer_id_arg,
    infer_resource,
    inferred_catalog_overrides,
)
from authorization_in_the_middle.service_conventions import (
    _find_catalog_builder,
    _find_resource_builder,
    _find_write_plan_fn,
    _import_entities_module,
    _principal_uid,
    _resolve_principal,
)
from flask import current_app, g, jsonify, request
from logenvelope.flask import cedar_principal_log_fields, log_request_event
from werkzeug.exceptions import BadRequest


class EvaluatorProxy:
    def is_authorized(self, *args: Any, **kwargs: Any) -> bool:
        return current_app.extensions["cedar_evaluator"].is_authorized(*args, **kwargs)


evaluator_proxy = EvaluatorProxy()


def with_security(
    action: str | None = None,
    resource: str | None = None,
    resource_fn: Callable[[], str] | None = None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None = None,
    namespace: str | None = None,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
    id_arg: str | None = None,
    rate_limit: str = "60 per minute",
    enforce_active_actor: bool = True,
    resource_type: str | None = None,
    catalog_id: str | None = None,
    catalog_id_from: str | None = None,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
    entity_module: str | None = None,
    validate_openapi: bool = False,
    openapi_spec_path: str | None = None,
    context_fn: Callable[[], dict[str, Any]] | None = None,
) -> Callable:
    """
    JWT authentication + Cedar authorization for a Flask route.

    **Default (omit ``action``):** infer CRUD **Action** from method + path. For
    inferred ``create`` / ``update``, automatically validate the body against
    ``openapi.json``, attach ``presentFields`` from raw JSON keys, and authorize
    against the service write record via
    ``src.services.{model}_service.plan_*_from_openapi`` and
    ``src.authorization.entities.build_write_{model}_entity``.

    **Overrides:** pass ``action``, ``resource_fn``, ``entities_fn``, ``id_arg``, etc.
    for non-CRUD routes (provision, rotate credentials, nested list actions). Pass
    ``validate_openapi=True`` when a custom action still accepts a JSON body.

    Sets ``g.validated_body``, ``g.planned_body``, ``g.present_fields``, and
    ``g.write_resource`` on REST writes.

    ``src.authorization.entities`` must provide ``NAMESPACE``, ``resolve_principal()``, and
    optionally ``registry_{model}_cedar_attrs`` / ``member_attrs`` for synthesized builders.
    Named ``build_*`` hooks remain supported as overrides.
    """
    if action is not None and resource is not None:
        raise TypeError("with_security: pass action or resource, not both")

    def decorator(f: Callable) -> Callable:
        entities_mod = _import_entities_module()
        crud_resource = resource
        use_crud_inference = action is None
        write_record: dict[str, Any] | None = None
        request_present_fields: list[str] = []
        auto_catalog = catalog_id_from is None and catalog_attrs is None

        def _resolved_catalog() -> tuple[str | None, Any]:
            if not auto_catalog:
                return catalog_id_from, catalog_attrs
            overrides = inferred_catalog_overrides()
            return (
                catalog_id_from or overrides.get("catalog_id_from"),
                catalog_attrs if catalog_attrs is not None else overrides.get("catalog_attrs"),
            )

        def _infer_kw_at_request() -> dict[str, Any]:
            resolved_catalog_id_from, resolved_catalog_attrs = _resolved_catalog()
            return _infer_kwargs(
                resource_fn=resource_fn,
                entities_fn=entities_fn,
                namespace=namespace,
                id_arg=id_arg,
                resource_type=resource_type,
                catalog_id=catalog_id,
                catalog_id_from=resolved_catalog_id_from,
                catalog_attrs=resolved_catalog_attrs,
                entity_module=entity_module,
                entities_mod=entities_mod,
                resource_loader=resource_loader,
            )

        inferred_namespace = namespace
        if inferred_namespace is None and entities_mod is not None:
            inferred_namespace = getattr(entities_mod, "NAMESPACE", None)

        def _authorize_write_entities(act: str) -> list[dict[str, Any]] | None:
            if write_record is None:
                return None
            model_name, verb = _action_parts(act)
            if verb in ("create", "update"):
                return _entities_for_write_member(
                    entities_mod,
                    model_name,
                    write_record,
                    present_fields=request_present_fields or None,
                    namespace=inferred_namespace,
                    id_arg=id_arg,
                    builder_module_name=entity_module or model_name,
                )
            return None

        def _authorize_write_resource_uid(act: str) -> str | None:
            if write_record is None:
                return None
            model_name, verb = _action_parts(act)
            if verb == "create":
                return _resource_uid_for_write_member(
                    entities_mod,
                    model_name,
                    write_record,
                    namespace=inferred_namespace,
                    id_arg=id_arg,
                    builder_module_name=entity_module or model_name,
                )
            if verb == "update":
                member_arg = _resolve_id_arg(id_arg, model_name)
                resource_id = request_view_arg(member_arg)
                try:
                    model_mod = importlib.import_module(f"src.models.{entity_module or model_name}")
                except ImportError:
                    model_mod = None
                build_resource_entity = _find_resource_builder(
                    entities_mod,
                    model_mod,
                    model_name,
                    entity_module or model_name,
                    namespace=inferred_namespace,
                    id_arg=member_arg,
                )
                entity = build_resource_entity(resource_id, write_record)
                return _resource_uid_from_entity(entity)
            return None

        if use_crud_inference:
            def resolved_action() -> str:
                return infer_crud_action(crud_resource, id_arg=id_arg)

            def resolved_resource_fn() -> str:
                act = resolved_action()
                write_uid = _authorize_write_resource_uid(act)
                if write_uid is not None:
                    return write_uid
                rf, _, _, _ = _infer_rest_fns(act, **_infer_kw_at_request())
                return rf()

            def resolved_entities_fn() -> list[dict[str, Any]]:
                act = resolved_action()
                write_entities = _authorize_write_entities(act)
                if write_entities is not None:
                    return write_entities
                _, ef, _, _ = _infer_rest_fns(act, **_infer_kw_at_request())
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
                    **_infer_kw_at_request(),
                )

        def resolved_context_fn() -> dict[str, Any]:
            ctx = request_context()
            if context_fn is not None:
                ctx.update(context_fn())
            return ctx

        authz_decorator = with_authorization(
            evaluator_proxy,
            principal_fn=lambda em=entities_mod: _principal_uid(em),
            action=action_for_authz,
            resource_fn=resource_fn_local,
            entities_fn=entities_fn_local,
            context_fn=resolved_context_fn,
            log_event=log_request_event,
        )

        authn_decorator = with_authentication(enforce_active_actor=enforce_active_actor)

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal write_record, request_present_fields
            http_method = request.method.upper()
            rest_write = False
            if use_crud_inference and http_method in ("POST", "PUT", "PATCH"):
                inferred = infer_crud_action(crud_resource, id_arg=id_arg)
                _, inferred_verb = _action_parts(inferred)
                rest_write = inferred_verb in ("create", "update")
            parse_openapi = validate_openapi or rest_write
            if parse_openapi and http_method in ("POST", "PUT", "PATCH"):
                try:
                    validated_body, present_fields, _ = parse_flask_request_body(
                        spec_path=openapi_spec_path,
                    )
                    g.validated_body = validated_body
                    g.planned_body = dict(validated_body)
                    g.present_fields = present_fields
                    request_present_fields = present_fields
                except (ValueError, BadRequest) as exc:
                    message = exc.description if isinstance(exc, BadRequest) else str(exc)
                    return jsonify({"error": "invalid_request", "message": message}), 400
            if rest_write:
                builder_module = entity_module
                if builder_module is None:
                    builder_module = _action_parts(infer_crud_action(crud_resource, id_arg=id_arg))[0]
                plan_fn = _find_write_plan_fn(builder_module, http_method)
                if plan_fn is None:
                    return jsonify({
                        "error": "invalid_request",
                        "message": (
                            f"REST {http_method} requires "
                            f"src.services.{builder_module}_service.plan_*_from_openapi"
                        ),
                    }), 500
                try:
                    write_record = plan_fn()
                    g.write_resource = write_record
                except (ValueError, BadRequest) as exc:
                    message = exc.description if isinstance(exc, BadRequest) else str(exc)
                    return jsonify({"error": "invalid_request", "message": message}), 400
            try:
                principal_entity = _resolve_principal(entities_mod)
                principal_fields = cedar_principal_log_fields(principal_entity)
            except Exception:
                principal_fields = {"principal": "unknown"}

            log_resource_name = resolved_resource_name
            log_target_id_arg = target_id_arg
            if use_crud_inference:
                act = infer_crud_action(crud_resource, id_arg=id_arg)
                _, _, log_resource_name, log_target_id_arg = _infer_rest_fns(
                    act, **_infer_kw_at_request()
                )

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
