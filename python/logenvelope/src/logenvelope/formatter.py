"""JSON log record formatter."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as a single JSON line."""

    def __init__(self, default_event_type: str | None = None) -> None:
        super().__init__()
        self.default_event_type = default_event_type

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        event_type = getattr(record, "event_type", None)
        if event_type is None:
            event_type = self.default_event_type
        if event_type is not None:
            entry["event_type"] = event_type
        extra = getattr(record, "extra_fields", None)
        if extra is not None:
            entry.update(extra)
        return json.dumps(entry)
