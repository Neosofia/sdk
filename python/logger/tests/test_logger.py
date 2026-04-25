"""Tests for neosofia_logger.

Output is validated against the platform log envelope schema.
The schema is loaded from a URL by default; set SCHEMAS_DIR in the
environment to load it from a local path (useful for offline dev).
"""
from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import urllib.request

import jsonschema
import pytest

from neosofia_logger import JSONFormatter, emits, log_event, setup_logging


_SCHEMAS_BASE_URL = "https://raw.githubusercontent.com/Neosofia/schemas/main"
_SCHEMAS_DIR = os.environ.get("SCHEMAS_DIR")


def _load_schema(filename: str) -> dict:
    if _SCHEMAS_DIR:
        path = pathlib.Path(_SCHEMAS_DIR) / filename
        return json.loads(path.read_text())
    url = f"{_SCHEMAS_BASE_URL}/{filename}"
    with urllib.request.urlopen(url) as resp:  # noqa: S310 — pinned constant
        return json.loads(resp.read())


@pytest.fixture(scope="session")
def log_schema() -> dict:
    return _load_schema("log-v1.0.0.json")


@pytest.fixture
def captured_logger():
    """Replace the logger's handler with one writing to an in-memory buffer."""
    buffer = io.StringIO()
    logger = setup_logging("test_service")
    logger.handlers.clear()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    yield logger, buffer
    logger.handlers.clear()


def test_setup_logging_returns_logger():
    logger = setup_logging("svc-a")
    assert logger.name == "svc-a"
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_setup_logging_respects_explicit_level():
    logger = setup_logging("svc-b", level="DEBUG")
    assert logger.level == logging.DEBUG


def test_emits_attaches_event_types():
    @emits("event_a", "event_b")
    def fn():
        return "called"

    assert fn.__emits__ == ["event_a", "event_b"]
    assert fn() == "called"  # decorator does not wrap


def test_log_event_produces_schema_conformant_output(captured_logger, log_schema):
    _logger, buffer = captured_logger
    log_event(
        "platform_token_issued",
        actor="clinician:usr_abc123",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
    )
    line = buffer.getvalue().strip()
    assert line, "no log output captured"
    entry = json.loads(line)

    jsonschema.validate(entry, log_schema)

    assert entry["event_type"] == "platform_token_issued"
    assert entry["actor"] == "clinician:usr_abc123"
    assert entry["level"] == "INFO"


def test_log_event_with_only_event_type(captured_logger, log_schema):
    _logger, buffer = captured_logger
    log_event("health_check_failed")
    entry = json.loads(buffer.getvalue().strip())
    jsonschema.validate(entry, log_schema)
    assert entry["event_type"] == "health_check_failed"


def test_jsonformatter_minimal_record(log_schema):
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    entry = json.loads(JSONFormatter().format(record))
    jsonschema.validate(entry, log_schema)
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert "event_type" not in entry
