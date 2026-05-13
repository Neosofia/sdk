import importlib
from functools import wraps
from typing import Callable, Any

from flask import current_app, request
from authentication_in_the_middle.decorators import with_authentication
from authorization_in_the_middle.decorators import with_authorization
from authorization_in_the_middle.flask_identity import (
    extract_jwt_principal_uid,
    extract_jwt_principal_entity,
    entity_uid
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

def default_log_event(event_type: str, **kwargs):
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
    require_role: bool = True,
) -> Callable:
    """
    Unified security decorator for Neosofia API services.
    Enforces rate limiting, JWT authentication, and Cedar authorization in one step.
    Allows for dynamic discovery of models and services.
    """
    def decorator(f: Callable) -> Callable:
        resource_fn_local = resource_fn
        entities_fn_local = entities_fn
        
        action_key = action[len('Action::"'):-1] if action.startswith('Action::"') else action
        model_name = action_key.split(":", 1)[0].replace("-", "_").lower()
        target_id_arg = id_arg or f"{model_name}_id"
        resolved_resource_name = "".join(part.capitalize() for part in model_name.split("_"))

        if resource_fn_local is None or entities_fn_local is None:
            resource_name = resolved_resource_name
            inferred_namespace = namespace
            inferred_loader = resource_loader
            inferred_builder = build_resource_entity
            
            if inferred_namespace is None or inferred_builder is None or inferred_loader is None:
                try:
                    if inferred_loader is None:
                        service_mod = importlib.import_module(f"src.services.{model_name}_service")
                        inferred_loader = getattr(service_mod, f"get_{model_name}_or_404")
                    
                    if inferred_builder is None or inferred_namespace is None:
                        model_mod = importlib.import_module(f"src.models.{model_name}")
                        if inferred_builder is None:
                            inferred_builder = getattr(model_mod, f"build_{model_name}_entity")
                        if inferred_namespace is None:
                            inferred_namespace = getattr(model_mod, "NAMESPACE")
                except (ImportError, AttributeError) as e:
                    raise ValueError(
                        f"Could not infer authorization helpers for '{model_name}'. "
                        f"Please provide namespace, resource_loader, and build_resource_entity explicitly. Error: {e}"
                    )
            
            if resource_fn_local is None:
                resource_fn_local = lambda: _resource_uid_from_view_arg(
                    inferred_namespace,
                    resource_name,
                    id_arg=target_id_arg,
                    loader=inferred_loader,
                )
            if entities_fn_local is None:
                entities_fn_local = lambda: _authorization_entities_for_resource(
                    inferred_namespace,
                    inferred_builder,
                    inferred_loader,
                    id_arg=target_id_arg,
                )
        else:
            inferred_namespace = namespace

        authz_decorator = with_authorization(
            evaluator_proxy,
            principal_fn=lambda: extract_jwt_principal_uid(inferred_namespace),
            action=action,
            resource_fn=resource_fn_local,
            entities_fn=entities_fn_local,
            context_fn=request_context,
            log_event=default_log_event,
        )
        
        # Uses lazy config lookup so no args required here
        authn_decorator = with_authentication(require_role=require_role)

        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Log event 
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
                "resource_id": kwargs.get(target_id_arg),
                "rate_limit": rate_limit,
            }
            if trace_id:
                log_kwargs["trace_id"] = trace_id

            default_log_event("security_evaluation_started", **log_kwargs)
            return authz_decorator(f)(*args, **kwargs)
            
        final_handler = authn_decorator(wrapper)
        
        # Try to dynamically stack the rate limiter at import time using project conventions
        try:
            from src.bootstrap.extensions import limiter
            final_handler = limiter.limit(rate_limit)(final_handler)
        except ImportError:
            pass # No limiter installed in this project
            
        return final_handler
    
    return decorator
