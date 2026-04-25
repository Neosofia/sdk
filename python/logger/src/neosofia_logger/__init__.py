"""Structured JSON logger for Neosofia platform services.

Output conforms to the platform log envelope schema:
https://github.com/Neosofia/schemas/blob/main/log-v1.0.0.json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

__all__ = ["JSONFormatter", "setup_logging", "log_event", "emits"]

_DEFAULT_LOGGER_NAME = "neosofia"
_logger_name = _DEFAULT_LOGGER_NAME


class JSONFormatter(logging.Formatter):
    """Format log records as a single JSON line conforming to log-v1.0.0.json."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        event_type = getattr(record, "event_type", None)
        if event_type is not None:
            entry["event_type"] = event_type
        extra = getattr(record, "extra_fields", None)
        if extra is not None:
            entry.update(extra)
        return json.dumps(entry)


def setup_logging(name: str = _DEFAULT_LOGGER_NAME, level: str | None = None) -> logging.Logger:
    """Configure a JSON-formatted stream logger for this process.

    The logger name is also used by ``log_event`` for subsequent calls
    in the same process.

    Args:
        name: Logger name (typically the service name, e.g. ``"authentication"``).
        level: Log level. Defaults to the ``LOG_LEVEL`` environment variable or ``INFO``.

    Returns:
        The configured :class:`logging.Logger` instance.
    """
    global _logger_name
    _logger_name = name
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    return logger


def emits(*event_types: str) -> Callable:
    """Decorator — declares the log event types a function may emit.

    Stores event types on the function as ``__emits__`` for introspection.
    Pure metadata; does not wrap the call.
    """
    def decorator(fn: Callable) -> Callable:
        fn.__emits__ = list(event_types)  # type: ignore[attr-defined]
        return fn
    return decorator


def log_event(event_type: str, **kwargs: object) -> None:
    """Emit a structured log event at INFO level.

    Args:
        event_type: Machine-readable event identifier (e.g. ``"platform_token_issued"``).
        **kwargs: Additional fields merged into the JSON envelope (e.g. ``actor``,
            ``trace_id``, ``reason``).
    """
    logger = logging.getLogger(_logger_name)
    record = logger.makeRecord(logger.name, logging.INFO, "", 0, "", (), None)
    record.event_type = event_type  # type: ignore[attr-defined]
    record.extra_fields = kwargs  # type: ignore[attr-defined]
    logger.handle(record)
