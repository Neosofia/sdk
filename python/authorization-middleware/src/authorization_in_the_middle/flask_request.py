"""Flask request helpers shared by route inference and authorization."""
from __future__ import annotations

from typing import Any

from flask import request


def request_context() -> dict[str, Any]:
    return {"http_method": request.method, "route": request.url_rule.rule if request.url_rule else ""}


def request_view_arg(arg_name: str) -> str:
    return request.view_args[arg_name] if request.view_args and arg_name in request.view_args else ""
