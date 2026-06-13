"""Parse the service OpenAPI contract for request validation and Cedar ``presentFields``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, RefResolver, ValidationError

from authorization_in_the_middle.payload import present_field_names

_ROUTE_PARAM = re.compile(r"<(?:\w+:)?(\w+)>")


_startup_spec: dict[str, Any] | None = None
_startup_spec_path: str | None = None
_ad_hoc_specs: dict[str, dict[str, Any]] = {}
_resolvers: dict[str, RefResolver] = {}
_body_validators: dict[tuple[str, str], Draft202012Validator] = {}


def flask_rule_to_openapi_path(rule: str) -> str:
    """``/api/v1/users/<user_uuid>`` → ``/api/v1/users/{user_uuid}``."""
    return _ROUTE_PARAM.sub(r"{\1}", rule)


def load_openapi_spec(path: Path | str) -> dict[str, Any]:
    """Load ``openapi.json`` from disk."""
    spec_path = Path(path)
    with spec_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def init_openapi_spec(path: Path | str) -> dict[str, Any]:
    """Load and cache the OpenAPI contract (call once at service startup)."""
    global _startup_spec, _startup_spec_path
    resolved = str(Path(path).resolve())
    _startup_spec = load_openapi_spec(resolved)
    _startup_spec_path = resolved
    return _startup_spec


def bind_openapi_spec(app: Any) -> dict[str, Any]:
    """Read ``OPENAPI_SPEC_PATH`` from the Flask app and cache the contract at startup."""
    configured = app.config.get("OPENAPI_SPEC_PATH")
    if not configured:
        raise RuntimeError("OPENAPI_SPEC_PATH must be set before bind_openapi_spec(app)")
    return init_openapi_spec(configured)


def openapi_spec_path() -> str | None:
    """Resolved path of the startup-bound spec, if any."""
    return _startup_spec_path


def reset_openapi_spec_cache() -> None:
    """Clear cached specs (tests only)."""
    global _startup_spec, _startup_spec_path
    _startup_spec = None
    _startup_spec_path = None
    _ad_hoc_specs.clear()
    _resolvers.clear()
    _body_validators.clear()


def _spec_cache_key(spec: dict[str, Any], spec_path: Path | str | None = None) -> str:
    if spec_path is not None:
        return str(Path(spec_path).resolve())
    if _startup_spec is not None and spec is _startup_spec and _startup_spec_path is not None:
        return _startup_spec_path
    for path, cached in _ad_hoc_specs.items():
        if cached is spec:
            return path
    return str(id(spec))


def _resolver_for_spec(spec: dict[str, Any], spec_key: str) -> RefResolver:
    resolver = _resolvers.get(spec_key)
    if resolver is None:
        resolver = RefResolver.from_schema(spec)
        _resolvers[spec_key] = resolver
    return resolver


def _schema_cache_key(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True)


def _body_validator(
    schema: dict[str, Any],
    spec: dict[str, Any],
    spec_key: str,
) -> Draft202012Validator:
    cache_key = (spec_key, _schema_cache_key(schema))
    cached = _body_validators.get(cache_key)
    if cached is not None:
        return cached
    validator = Draft202012Validator(
        schema,
        resolver=_resolver_for_spec(spec, spec_key),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    _body_validators[cache_key] = validator
    return validator


def resolve_openapi_spec(path: Path | str | None = None) -> dict[str, Any]:
    """Return the startup-bound spec, or an ad-hoc path for tests."""
    if path is not None:
        key = str(Path(path).resolve())
        cached = _ad_hoc_specs.get(key)
        if cached is None:
            cached = load_openapi_spec(key)
            _ad_hoc_specs[key] = cached
        return cached
    if _startup_spec is not None:
        return _startup_spec
    raise RuntimeError(
        "OpenAPI spec is not bound; call bind_openapi_spec(app) during create_app"
    )


def operation_for_request(
    spec: dict[str, Any],
    *,
    rule: str,
    method: str,
) -> dict[str, Any] | None:
    """Return the OpenAPI operation object for a Flask rule and HTTP method."""
    openapi_path = flask_rule_to_openapi_path(rule)
    path_item = spec.get("paths", {}).get(openapi_path)
    if not path_item:
        return None
    operation = path_item.get(method.lower())
    return operation if isinstance(operation, dict) else None


def request_body_schema(operation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract the ``application/json`` request body schema from an operation."""
    if not operation:
        return None
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content", {})
    json_content = content.get("application/json")
    if not isinstance(json_content, dict):
        return None
    schema = json_content.get("schema")
    return schema if isinstance(schema, dict) else None


def first_validation_message(exc: ValidationError) -> str:
    """Pick the most specific jsonschema error message for a 400 response."""
    if not exc.context:
        path = ".".join(str(part) for part in exc.path)
        if path:
            return f"{path}: {exc.message}"
        return exc.message
    child = exc.context[0]
    path = ".".join(str(part) for part in child.path)
    if path:
        return f"{path}: {child.message}"
    return child.message


def validate_request_body(
    body: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    *,
    spec_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate a JSON body against an OpenAPI schema; raise ``ValueError`` on failure."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    if not body and schema.get("type") == "object":
        raise ValueError("body must be a JSON object")
    validator = _body_validator(schema, spec, _spec_cache_key(spec, spec_path))
    try:
        validator.validate(body)
    except ValidationError as exc:
        raise ValueError(first_validation_message(exc)) from exc
    return body


def parse_flask_request_body(
    *,
    spec_path: Path | str | None = None,
    rule: str | None = None,
    method: str | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    """
    Validate the current Flask JSON body against the OpenAPI operation schema.

    Returns ``(validated_body, present_fields, operation)``.
    ``present_fields`` is sorted keys from the **raw** body (for Cedar).
    """
    from flask import request

    spec = resolve_openapi_spec(spec_path)
    spec_key = _spec_cache_key(spec, spec_path)
    resolved_rule = rule or (request.url_rule.rule if request.url_rule else request.path)
    resolved_method = (method or request.method).lower()
    operation = operation_for_request(spec, rule=resolved_rule, method=resolved_method)
    raw = request.get_json(silent=True)
    raw_body = raw if isinstance(raw, dict) else {}
    present_fields = present_field_names(raw_body)
    schema = request_body_schema(operation)
    if schema is None:
        if raw_body:
            raise ValueError("request body is not defined for this operation")
        return {}, present_fields, operation
    validated = validate_request_body(raw_body, schema, spec, spec_path=spec_key)
    return validated, present_fields, operation
