"""Process-wide logger configuration."""
from __future__ import annotations

import logging
import os

from logenvelope import state
from logenvelope.formatter import JSONFormatter


def setup_logging(name: str, level: str | None = None) -> logging.Logger:
    """Configure a JSON-formatted stream logger for this process.

    The logger name is also used by ``log_event`` for subsequent calls
    in the same process.

    Args:
        name: Logger name (typically the service name, e.g. ``"authentication"``).
        level: Log level. Defaults to the ``LOG_LEVEL`` environment variable or ``INFO``.

    Returns:
        The configured :class:`logging.Logger` instance.
    """
    state.logger_name = name
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    return logger
