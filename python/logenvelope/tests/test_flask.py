"""Tests for logenvelope.flask request telemetry helpers."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask

from logenvelope import setup_logging
from logenvelope.flask import (
    cedar_principal_log_fields,
    default_log_event,
    log_request_event,
    log_request_handled,
    register_logenvelope_extension,
    request_log_fields,
)

pytest.importorskip("flask")


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    setup_logging("test_service")
    register_logenvelope_extension(flask_app)
    return flask_app


def test_request_log_fields_empty_outside_context():
    assert request_log_fields() == {}


def test_request_log_fields_from_request(app):
    with app.test_request_context(
        "/api/v1/items",
        method="POST",
        headers={"traceparent": "00-abc123def4567890abc123def4567890-abc123def4567890-01"},
    ):
        assert request_log_fields() == {
            "http.method": "POST",
            "http.route": "/api/v1/items",
            "trace_id": "00-abc123def4567890abc123def4567890-abc123def4567890-01",
        }


def test_cedar_principal_log_fields_maps_entity_attrs():
    entity = {
        "uid": {"__entity": {"type": "cdp::Clinician", "id": "usr-1"}},
        "attrs": {"tenantId": "tenant-1", "tenantType": "platform"},
    }
    assert cedar_principal_log_fields(entity) == {
        "principal": 'cdp::Clinician::"usr-1"',
        "tenant_uuid": "tenant-1",
        "tenant_type": "platform",
    }


@patch("logenvelope.flask.default_log_event")
def test_log_request_event_merges_request_context(mock_emit, app):
    with app.test_request_context("/health", method="GET"):
        log_request_event(
            "authentication.failed",
            level=logging.WARNING,
            reason="missing_bearer",
            http_status_code=401,
        )
    mock_emit.assert_called_once_with(
        "authentication.failed",
        level=logging.WARNING,
        **{
            "http.method": "GET",
            "http.route": "/health",
            "reason": "missing_bearer",
            "http_status_code": 401,
        },
    )


@patch("logenvelope.flask.default_log_event")
def test_log_request_handled_emits_expected_fields(mock_emit, app):
    with app.test_request_context(
        "/api/v1/messages",
        method="POST",
        headers={"X-Transaction-Id": "txn-123"},
    ):
        log_request_handled(
            "message_create",
            201,
            source={"channel": 3, "channel_label": "sms"},
            copy_from_source=("channel", "channel_label"),
        )

    mock_emit.assert_called_once_with(
        "http.request_handled",
        level=logging.INFO,
        **{
            "http.method": "POST",
            "http.route": "/api/v1/messages",
            "trace_id": "txn-123",
            "http.status_code": 201,
            "operation": "message_create",
            "channel": 3,
            "channel_label": "sms",
        },
    )


def test_default_log_event_uses_extension_when_present(app):
    calls: list[tuple[str, dict]] = []

    def capture(event_type: str, **kwargs):
        calls.append((event_type, kwargs))

    app.extensions["logenvelope"] = SimpleNamespace(log_event=capture)
    with app.test_request_context("/"):
        default_log_event("custom.event", foo="bar")
    assert calls == [("custom.event", {"level": logging.INFO, "foo": "bar"})]


def test_register_logenvelope_extension_accepts_custom_emitter(app):
    calls: list[str] = []

    def custom_emit(event_type: str, **kwargs):
        calls.append(event_type)

    register_logenvelope_extension(app, log_event=custom_emit)
    with app.test_request_context("/"):
        app.extensions["logenvelope"].log_event("wired")
    assert calls == ["wired"]


@patch("logenvelope.flask.default_log_event")
def test_log_request_handled_skips_missing_source_keys(mock_emit, app):
    with app.test_request_context("/api/v1/interactions", method="GET"):
        log_request_handled(
            "interaction_list",
            200,
            source={"interaction_uuid": "abc"},
            copy_from_source=("channel",),
        )
    kwargs = mock_emit.call_args[1]
    assert "channel" not in kwargs
    assert kwargs["operation"] == "interaction_list"
