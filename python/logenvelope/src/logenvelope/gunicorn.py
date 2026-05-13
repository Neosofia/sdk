"""Gunicorn helpers for structured JSON access logging."""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from logenvelope.formatter import JSONFormatter

try:
    from gunicorn.glogging import Logger as _GunicornLogger
except ImportError:  # pragma: no cover
    _GunicornLogger = object

_REQUEST_LINE_RE = re.compile(r"(?P<method>[^ ]+) (?P<target>[^ ]+) (?P<protocol>[^ ]+)")


def _clean(value: Any) -> str:
    if value in (None, "-"):
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    value = str(value)
    return value or ""


def _parse_request_line(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    match = _REQUEST_LINE_RE.match(value)
    return match.groupdict() if match else None


def _access_fields(args: Mapping[str, Any]) -> dict[str, object]:
    atoms = dict(args)
    target = _clean(atoms.get("U"))
    query = _clean(atoms.get("q"))
    if target and query:
        target = f"{target}?{query}"

    def int_field(name: str) -> int | str:
        value = atoms.get(name)
        if value in (None, "-"):
            return ""
        try:
            return int(value)
        except (TypeError, ValueError):
            return ""

    fields: dict[str, object] = {
        "client.ip": _clean(atoms.get("h")),
        "remote.user": _clean(atoms.get("u")),
        "http.method": _clean(atoms.get("m")),
        "http.target": target,
        "http.protocol": _clean(atoms.get("H")),
        "http.user_agent": _clean(atoms.get("a")),
        "http.referer": _clean(atoms.get("f")),
        "http.response_time_us": int_field("D"),
        "process.pid": _clean(atoms.get("p")).replace("<", "").replace(">", ""),
    }

    fields["http.status_code"] = int_field("s")
    fields["http.response_size"] = int_field("B") or int_field("b")
    request_line = _clean(atoms.get("r"))
    if request_line:
        fields["http.request_line"] = request_line
        parsed = _parse_request_line(request_line)
        if parsed:
            fields.setdefault("http.method", parsed["method"])
            fields.setdefault("http.target", parsed["target"])
            fields.setdefault("http.protocol", parsed["protocol"])

    return fields


class GunicornAccessLogFormatter(JSONFormatter):
    """Format Gunicorn access log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        if record.name == "gunicorn.access":
            access_fields = _access_fields(record.args)
            if access_fields:
                extra = getattr(record, "extra_fields", None)
                record.extra_fields = {**(extra or {}), **access_fields}
            record.msg = ""
            record.args = ()
        return super().format(record)


class JSONLogger(_GunicornLogger):
    """Gunicorn logger class that emits structured JSON for access and error logs."""

    def setup(self, cfg) -> None:  # type: ignore[override]
        if _GunicornLogger is object:
            raise RuntimeError(
                "gunicorn is required to use logenvelope.gunicorn.JSONLogger"
            )

        super().setup(cfg)

        self._set_formatter(self.error_log, JSONFormatter())
        self._set_formatter(self.access_log, GunicornAccessLogFormatter(default_event_type="http.access"))

    def _set_formatter(self, log: logging.Logger, formatter: logging.Formatter) -> None:
        for handler in log.handlers:
            handler.setFormatter(formatter)
