"""Infer Cedar CRUD actions and resource names from Flask route rules."""
from __future__ import annotations

import re
from typing import Any

import inflect
from flask import has_request_context, request

_ROUTE_PREFIX_SEGMENTS = frozenset({"api"})
_VERSION_SEGMENT = re.compile(r"^v\d+$", re.IGNORECASE)
_PARAM = re.compile(r"^<(?:\w+:)?(\w+)>$")
_INFLECT = inflect.engine()


def _singularize(segment: str) -> str:
    singular = _INFLECT.singular_noun(segment)
    return singular if singular else segment


def _route_rule() -> str:
    if has_request_context() and request.url_rule:
        return request.url_rule.rule
    return request.path if has_request_context() else ""


def _route_tokens(rule: str) -> list[tuple[str, str]]:
    """Ordered ``('noun', segment)`` and ``('param', name)`` tokens from a Flask rule."""
    tokens: list[tuple[str, str]] = []
    for segment in rule.split("/"):
        if not segment or segment in _ROUTE_PREFIX_SEGMENTS or _VERSION_SEGMENT.match(segment):
            continue
        param_match = _PARAM.match(segment)
        if param_match:
            tokens.append(("param", param_match.group(1)))
        else:
            tokens.append(("noun", segment))
    return tokens


def _route_noun_segments(rule: str) -> list[str]:
    return [value for kind, value in _route_tokens(rule) if kind == "noun"]


def _last_noun_index(tokens: list[tuple[str, str]]) -> int | None:
    indices = [index for index, (kind, _) in enumerate(tokens) if kind == "noun"]
    return indices[-1] if indices else None


def _param_to_cedar_attr(param_name: str) -> str:
    """``tenant_uuid`` → ``tenantId``; ``slug`` → ``slug``."""
    if param_name.endswith("_uuid"):
        base = param_name[: -len("_uuid")]
        if not base:
            return param_name
        return f"{base[0].lower()}{base[1:]}Id" if len(base) > 1 else f"{base}Id"
    return param_name


_MEMBER_SUBRESOURCE_NOUNS = frozenset({
    "audits",
    "invites",
    "messages",
    "recoveries",
    "rotate",
    "inbox",
    "summary",
})


def _param_matches_preceding_noun(param_name: str, noun: str) -> bool:
    """``tenant_uuid`` after ``tenants``; ``slug`` after ``services`` does not match."""
    singular = _singularize(noun)
    prefixes = {singular, noun.rstrip("s")}
    return any(param_name.startswith(f"{prefix}_") for prefix in prefixes if prefix)


def _collect_scope_bindings(tokens: list[tuple[str, str]], end_index: int) -> list[tuple[str, str]]:
    scopes: list[tuple[str, str]] = []
    last_preceding_noun: str | None = None
    for kind, name in tokens[:end_index]:
        if kind == "noun":
            last_preceding_noun = name
            continue
        if kind == "param" and last_preceding_noun and _param_matches_preceding_noun(name, last_preceding_noun):
            scopes.append((name, _param_to_cedar_attr(name)))
    return scopes


def _route_layout(rule: str) -> tuple[str, str, str | None, list[tuple[str, str]]]:
    """
    Classify the route for inference.

    Returns ``(kind, resource_noun, member_param, scope_bindings)`` where kind is
    ``nested_collection``, ``member_subresource``, ``member``, ``simple``, or ``compound``.
    """
    tokens = _route_tokens(rule)
    nouns = [value for kind, value in tokens if kind == "noun"]
    if not nouns:
        raise ValueError(f"cannot infer resource from route {rule}")

    last_noun_idx = _last_noun_index(tokens)
    if last_noun_idx is None:
        return "simple", nouns[0], None, []

    for index, (kind, noun) in enumerate(tokens):
        if kind != "noun" or index + 1 >= len(tokens) or tokens[index + 1][0] != "param":
            continue
        param_name = tokens[index + 1][1]
        if not _param_matches_preceding_noun(param_name, noun):
            continue
        trailing = tokens[index + 2 :]
        if not trailing:
            return "member", noun, param_name, []
        trailing_nouns = [name for kind, name in trailing if kind == "noun"]
        if not trailing_nouns:
            return "member", noun, param_name, []
        trailing_noun = trailing_nouns[-1]
        if trailing_noun in _MEMBER_SUBRESOURCE_NOUNS:
            return "member_subresource", noun, param_name, []
        trailing_idx = next(
            index for index, (kind, name) in enumerate(tokens) if kind == "noun" and name == trailing_noun
        )
        return "nested_collection", trailing_noun, None, _collect_scope_bindings(tokens, trailing_idx)

    if len(nouns) == 1:
        return "simple", nouns[0], None, []
    return "compound", nouns[0], None, []


def infer_resource() -> str:
    """Infer Cedar resource from the route layout (nested, member, or compound)."""
    kind, resource_noun, _, _ = _route_layout(_route_rule())
    return _singularize(resource_noun)


def infer_scope_bindings(rule: str | None = None) -> list[tuple[str, str]]:
    """Path params that scope a nested collection (param name matches the preceding noun)."""
    _, _, _, scopes = _route_layout(rule or _route_rule())
    return scopes


def infer_catalog_scope() -> tuple[str | None, dict[str, str] | None]:
    """
    Nested collection scope for catalog authorization.

    ``/tenants/<tenant_uuid>/users`` → catalog id from ``tenant_uuid``,
    attrs ``{tenantId: ...}``.
    """
    if not has_request_context():
        return None, None
    scopes = infer_scope_bindings()
    if not scopes:
        return None, None
    view_args = request.view_args or {}
    attrs = {
        cedar_attr: str(view_args.get(param_name) or "")
        for param_name, cedar_attr in scopes
    }
    return scopes[-1][0], attrs


def infer_id_arg() -> str | None:
    """Member path param from route layout (nested member, subresource, or trailing param)."""
    kind, _, member_param, _ = _route_layout(_route_rule())
    if member_param and kind in ("member", "member_subresource"):
        return member_param
    tokens = _route_tokens(_route_rule())
    last_noun = _last_noun_index(tokens)
    if last_noun is None:
        return None
    for param_kind, name in tokens[last_noun + 1 :]:
        if param_kind == "param":
            return name
    return None


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


def inferred_catalog_overrides() -> dict[str, Any]:
    """Auto ``catalog_id_from`` / ``catalog_attrs`` when the route is nested."""
    catalog_id_from, catalog_attrs = infer_catalog_scope()
    overrides: dict[str, Any] = {}
    if catalog_id_from:
        overrides["catalog_id_from"] = catalog_id_from
    if catalog_attrs:
        overrides["catalog_attrs"] = catalog_attrs
    return overrides
