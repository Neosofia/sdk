import importlib
from functools import wraps
from typing import Any, Callable

from flask import current_app, request
from authentication_in_the_middle.decorators import with_authentication
from authorization_in_the_middle.decorators import with_authorization
from authorization_in_the_middle.flask_identity import (
    extract_jwt_principal_uid,
    extract_jwt_principal_entity,
    entity_uid,
)

class EvaluatorProxy:
    def is_authorized(self, *args: Any, **kwargs: Any) -> bool:
        return current_app.extensions["cedar_evaluator"].is_authorized(*args, **kwargs)

evaluator_proxy = EvaluatorProxy()

def request_context() -> dict[str, Any]:
    return {"http_method": request.method, "route": request.url_rule.rule if request.url_rule else ""}

def request_view_arg(arg_name: str) -> str:
    return request.view_args[arg_name] if request.view_args and arg_name in request.view_args else ""

def _resource_uid_from_view_arg(
    namespace: str,
    resource_name: str,
    id_arg: str,
    loader: Callable[[str], Any] | None = None,
) -> str:
    resource_id = request_view_arg(id_arg)
    if loader:
        loader(resource_id)
    return entity_uid(f"{namespace}::{resource_name}", resource_id)

def _resource_uid_for_catalog(namespace: str, resource_name: str, catalog_id: str) -> str:
    return entity_uid(f"{namespace}::{resource_name}", catalog_id)

def _authorization_entities_for_resource(
    namespace: str,
    build_resource_entity: Callable[[str, dict[str, Any]], dict[str, Any]],
    resource_loader: Callable[[str], dict[str, Any]],
    id_arg: str,
) -> list[dict[str, Any]]:
    resource_id = request_view_arg(id_arg)
    resource = resource_loader(resource_id)
    return [
        extract_jwt_principal_entity(namespace),
        build_resource_entity(resource_id, resource),
    ]

def default_log_event(event_type: str, **kwargs: Any) -> None:
    if "logenvelope" in current_app.extensions:
        current_app.extensions["logenvelope"].log_event(event_type, **kwargs)

def with_security(
    action: str,
    resource_fn: Callable[[], str] | None = None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None = None,
    namespace: str | None = None,
    build_resource_entity: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
    id_arg: str | None = None,
    rate_limit: str = "60 per minute",
    enforce_active_role: bool = True,
    resource_type: str | None = None,
    catalog_id: str | None = None,
    entity_module: str | None = None,
) -> Callable:
    """
    Unified security decorator for Neosofia API services.
    Enforces rate limiting, JWT authentication, and Cedar authorization in one step.
    Tier-1/Tier-2 access is decided only by Cedar policies, not JWT role presence checks.

    Convention (see templates/python/service):
    - action `document:read` infers model `document`, path `{document_id}`, loader
      `document_service.get_document_or_404`, builder `models.document.build_document_entity`.
    - resource_type overrides the Cedar entity type when it differs from the action prefix
      (e.g. action `user:read` on resource `Profile`).
    - catalog_id secures list/create endpoints against a fixed catalog resource.
    - entity_module selects which models package supplies the builder (default: action prefix).
    """
    def decorator(f: Callable) -> Callable:
        resource_fn_local = resource_fn
        entities_fn_local = entities_fn

        action_key = action[len('Action::"'):-1] if action.startswith('Action::"') else action
        model_name = action_key.split(":", 1)[0].replace("-", "_").lower()
        target_id_arg = id_arg or f"{model_name}_id"
        resolved_resource_name = resource_type or "".join(
            part.capitalize() for part in model_name.split("_")
        )
        builder_module_name = entity_module or model_name

        if resource_fn_local is None or entities_fn_local is None:
            inferred_namespace = namespace
            inferred_loader = resource_loader
            inferred_builder = build_resource_entity

            if inferred_namespace is None or inferred_builder is None or inferred_loader is None:
                try:
                    if inferred_loader is None:
                        service_mod = importlib.import_module(f"src.services.{model_name}_service")
                        inferred_loader = getattr(service_mod, f"get_{model_name}_or_404")

                    if inferred_builder is None or inferred_namespace is None:
                        model_mod = importlib.import_module(f"src.models.{builder_module_name}")
                        if inferred_builder is None:
                            inferred_builder = getattr(
                                model_mod,
                                f"build_{builder_module_name}_entity",
                            )
                        if inferred_namespace is None:
                            inferred_namespace = getattr(model_mod, "NAMESPACE")
                except (ImportError, AttributeError) as e:
                    raise ValueError(
                        f"Could not infer authorization helpers for '{model_name}'. "
                        f"Please provide namespace, resource_loader, and build_resource_entity "
                        f"explicitly. Error: {e}"
                    )

            if resource_fn_local is None:
                if catalog_id is not None:
                    if inferred_namespace is None:
                        raise ValueError("namespace is required when catalog_id is set")
                    resource_fn_local = lambda: _resource_uid_for_catalog(
                        inferred_namespace,
                        resolved_resource_name,
                        catalog_id,
                    )
                else:
                    resource_fn_local = lambda: _resource_uid_from_view_arg(
                        inferred_namespace,
                        resolved_resource_name,
                        id_arg=target_id_arg,
                        loader=inferred_loader,
                    )
            if entities_fn_local is None and catalog_id is None:
                entities_fn_local = lambda: _authorization_entities_for_resource(
                    inferred_namespace,
                    inferred_builder,
                    inferred_loader,
                    id_arg=target_id_arg,
                )
        else:
            inferred_namespace = namespace
            if catalog_id is not None and resource_fn_local is not None and entities_fn_local is not None:
                pass
            elif catalog_id is not None and resource_fn_local is None and inferred_namespace:
                resource_fn_local = lambda: _resource_uid_for_catalog(
                    inferred_namespace,
                    resolved_resource_name,
                    catalog_id,
                )

        authz_decorator = with_authorization(
            evaluator_proxy,
            principal_fn=lambda: extract_jwt_principal_uid(inferred_namespace or namespace or ""),
            action=action,
            resource_fn=resource_fn_local,
            entities_fn=entities_fn_local,
            context_fn=request_context,
            log_event=default_log_event,
        )

        authn_decorator = with_authentication(enforce_active_role=enforce_active_role)

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            trace_id = request.headers.get("traceparent") or request.headers.get("X-Transaction-Id")
            try:
                p_uid = extract_jwt_principal_uid(namespace)
            except Exception:
                p_uid = "unknown"

            log_kwargs = {
                "route": f.__name__,
                "principal": p_uid,
                "action": action,
                "resource_name": resolved_resource_name,
                "resource_id": catalog_id or kwargs.get(target_id_arg),
                "rate_limit": rate_limit,
            }
            if trace_id:
                log_kwargs["trace_id"] = trace_id

            default_log_event("security_evaluation_started", **log_kwargs)
            return authz_decorator(f)(*args, **kwargs)

        final_handler = authn_decorator(wrapper)

        try:
            from src.bootstrap.extensions import limiter
            final_handler = limiter.limit(rate_limit)(final_handler)
        except ImportError:
            pass

        return final_handler

    return decorator
