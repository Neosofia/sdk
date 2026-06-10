"""Request-scoped fields merged into authorization outcome logs."""
from __future__ import annotations

from typing import Any

from flask import g

_AUTHZ_OUTCOME_KEY = "authz_outcome_log_extra"


def set_authz_outcome_log_extra(**fields: Any) -> None:
    """Stash correlators from ``with_security`` for allow/deny outcome logs."""
    extra = {key: value for key, value in fields.items() if value is not None}
    setattr(g, _AUTHZ_OUTCOME_KEY, extra)


def authz_outcome_log_extra() -> dict[str, Any]:
    """Return stashed outcome correlators, or an empty dict when unset."""
    value = getattr(g, _AUTHZ_OUTCOME_KEY, None)
    if isinstance(value, dict):
        return value
    return {}
