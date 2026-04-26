"""
authentication-in-the-middle

Shared WorkOS session authentication middleware for Neosofia platform services.
Provides reusable decorators and utilities for protecting Flask routes.
"""

from authentication_in_the_middle.decorators import with_auth
from authentication_in_the_middle.session import (
    load_sealed_session,
    authenticate_session,
    refresh_session,
    revoke_session_cookie,
)

__version__ = "0.1.0"
__all__ = [
    "with_auth",
    "load_sealed_session",
    "authenticate_session",
    "refresh_session",
    "revoke_session_cookie",
]
