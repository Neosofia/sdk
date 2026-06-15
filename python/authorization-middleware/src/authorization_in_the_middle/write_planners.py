"""Default OpenAPI write planners when services omit custom hooks."""
from __future__ import annotations

from typing import Any

from authorization_in_the_middle.route_inference import infer_scope_bindings


def default_plan_create_from_openapi() -> dict[str, Any]:
    """Validated JSON body merged with nested collection path scope params."""
    from flask import g, request

    body = dict(getattr(g, "planned_body", None) or getattr(g, "validated_body", None) or {})
    view_args = request.view_args or {}
    for param_name, _cedar_attr in infer_scope_bindings():
        if param_name in view_args:
            body[param_name] = str(view_args[param_name])
    return body
