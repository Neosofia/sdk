"""Gunicorn-specific structured logging helpers."""
from __future__ import annotations

import json
import logging

from logenvelope.gunicorn import GunicornAccessLogFormatter


def test_gunicorn_access_log_formatter_structures_fields():
    formatter = GunicornAccessLogFormatter(default_event_type="http.access")
    record = logging.LogRecord(
        name="gunicorn.access",
        level=logging.INFO,
        pathname="/tmp/test.py",
        lineno=1,
        msg="%(h)s %(r)s %(s)s",
        args=(),
        exc_info=None,
    )
    record.args = {
        "h": "127.0.0.1",
        "r": "GET /ping HTTP/1.1",
        "s": "200",
        "m": "GET",
        "U": "/ping",
        "q": "",
        "H": "HTTP/1.1",
        "a": "curl/8.0",
        "f": "-",
        "B": "123",
        "D": "42000",
        "T": "0",
        "t": "[13/May/2026:03:21:00 +0000]",
        "p": "<83125>",
    }

    entry = json.loads(formatter.format(record))

    assert entry["event_type"] == "http.access"
    assert entry["message"] == ""
    assert entry["client.ip"] == "127.0.0.1"
    assert entry["http.method"] == "GET"
    assert entry["http.target"] == "/ping"
    assert entry["http.protocol"] == "HTTP/1.1"
    assert entry["http.status_code"] == 200
    assert entry["http.response_size"] == 123
    assert entry["http.user_agent"] == "curl/8.0"
    assert entry["http.response_time_us"] == 42000
    assert entry["process.pid"] == "83125"
