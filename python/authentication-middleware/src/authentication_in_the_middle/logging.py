from __future__ import annotations

import logging

from logenvelope.flask import log_request_event


def log_authentication_failed(
    *,
    reason: str,
    status_code: int,
    route: str,
    error_type: str | None = None,
) -> None:
    fields = {
        "reason": reason,
        "http.status_code": status_code,
        "route": route,
    }
    if error_type:
        fields["error_type"] = error_type
    log_request_event("authentication.failed", level=logging.WARNING, **fields)
