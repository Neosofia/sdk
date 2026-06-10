"""Flask helpers for structured request telemetry."""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from types import SimpleNamespace
from typing import Any

try:
    from flask import Flask, current_app, has_request_context, request
except ImportError:  # pragma: no cover
    Flask = object  # type: ignore[assignment,misc]
    current_app = None  # type: ignore[assignment]

    def has_request_context() -> bool:  # type: ignore[misc]
        return False

    request = None  # type: ignore[assignment]

_TRACE_HEADERS = ("traceparent", "X-Transaction-Id")


def default_log_event(event_type: str, *, level: int = logging.INFO, **kwargs: Any) -> None:
    """Emit via the app extension when wired, otherwise process-level ``log_event``."""
    if has_request_context() and "logenvelope" in current_app.extensions:
        current_app.extensions["logenvelope"].log_event(event_type, level=level, **kwargs)
        return
    try:
        from logenvelope.events import log_event
    except ImportError:
        return
    try:
        log_event(event_type, level=level, **kwargs)
    except RuntimeError:
        return


def request_log_fields() -> dict[str, Any]:
    """``http.method``, ``http.route``, and ``trace_id`` from the active Flask request."""
    if not has_request_context():
        return {}
    fields: dict[str, Any] = {
        "http.method": request.method,
        "http.route": request.path,
    }
    for header in _TRACE_HEADERS:
        trace_id = request.headers.get(header)
        if trace_id:
            text = str(trace_id).strip()
            if text:
                fields["trace_id"] = text
                break
    return fields


def cedar_principal_log_fields(principal_entity: Mapping[str, Any] | None) -> dict[str, Any]:
    """Principal UID and tenant correlators from a Cedar entity payload."""
    if not principal_entity:
        return {}
    fields: dict[str, Any] = {}
    ref = principal_entity.get("uid", {}).get("__entity")
    if isinstance(ref, dict) and ref.get("type") and ref.get("id") is not None:
        fields["principal"] = f'{ref["type"]}::"{ref["id"]}"'
    attrs = principal_entity.get("attrs")
    if isinstance(attrs, dict):
        if tenant_uuid := attrs.get("tenantId") or attrs.get("tenant_uuid"):
            fields["tenant_uuid"] = tenant_uuid
        if tenant_type := attrs.get("tenantType") or attrs.get("tenant_type"):
            fields["tenant_type"] = tenant_type
    return fields


def _fields_from_source(
    source: Mapping[str, Any] | None,
    keys: Sequence[str],
) -> dict[str, Any]:
    if not source:
        return {}
    fields: dict[str, Any] = {}
    for key in keys:
        if key in source and source[key] is not None:
            fields[key] = source[key]
    return fields


def register_logenvelope_extension(
    app: Flask,
    *,
    log_event: Callable[..., None] | None = None,
) -> None:
    """Expose ``log_event`` on ``app.extensions['logenvelope']`` for middleware and routes."""
    from logenvelope.events import log_event as _log_event

    emit = log_event or _log_event
    app.extensions["logenvelope"] = SimpleNamespace(log_event=emit)


def log_request_event(
    event_type: str,
    *,
    include_request: bool = True,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    """Emit a structured event, merging request correlators when ``include_request`` is true."""
    fields: dict[str, Any] = {}
    if include_request:
        fields.update(request_log_fields())
    fields.update(extra)
    default_log_event(event_type, level=level, **fields)


def log_request_handled(
    operation: str,
    status_code: int,
    *,
    event_type: str = "http.request_handled",
    source: Mapping[str, Any] | None = None,
    copy_from_source: Sequence[str] = (),
    **extra: Any,
) -> None:
    """Emit a structured route-outcome event for OR-001-style request telemetry dashboards."""
    log_request_event(
        event_type,
        **{"http.status_code": status_code},
        operation=operation,
        **_fields_from_source(source, copy_from_source),
        **extra,
    )
