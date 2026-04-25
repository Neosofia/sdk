"""Structured event emission and the @emits introspection decorator."""
from __future__ import annotations

import logging
from typing import Callable

from logenvelope import state


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

    ``setup_logging`` must have been called first to register the logger name.

    Args:
        event_type: Machine-readable event identifier (e.g. ``"platform_token_issued"``).
        **kwargs: Additional fields merged into the JSON envelope (e.g. ``actor``,
            ``trace_id``, ``reason``).
    """
    if state.logger_name is None:
        raise RuntimeError("log_event called before setup_logging")
    logger = logging.getLogger(state.logger_name)
    record = logger.makeRecord(logger.name, logging.INFO, "", 0, "", (), None)
    record.event_type = event_type  # type: ignore[attr-defined]
    record.extra_fields = kwargs  # type: ignore[attr-defined]
    logger.handle(record)
