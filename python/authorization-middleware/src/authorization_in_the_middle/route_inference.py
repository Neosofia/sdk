"""Infer Cedar CRUD actions and resource names from Flask route rules."""
from __future__ import annotations

import re

import inflect
from flask import request

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
