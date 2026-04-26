"""
Flask route decorators for WorkOS session-based authentication.

Provides the with_auth decorator factory for protecting routes that require
a valid WorkOS sealed session.
"""

from functools import wraps
from typing import Any, Callable

from flask import make_response, redirect, url_for

from authentication_in_the_middle.session import (
    authenticate_session,
    load_sealed_session,
    refresh_session,
)


def with_auth(
    workos_client,
    cookie_password: str,
    is_development: bool,
    log_event: Callable,
) -> Callable:
    """
    Decorator factory that requires a valid WorkOS session for a Flask route.

    Attempts to refresh expired sessions before denying access. On failure,
    redirects to the auth.login endpoint and clears the session cookie.

    Args:
        workos_client: WorkOS client with user_management interface.
        cookie_password: Password used to decrypt the sealed session cookie.
        is_development: Controls cookie Secure flag (False in development).
        log_event: Callable with signature log_event(event_type, **kwargs).

    Returns:
        A decorator that wraps a Flask view function.

    Example:
        _with_auth = with_auth(workos_client, cookie_password, is_dev, log_event)

        @bp.route("/protected")
        @_with_auth
        def protected():
            return "authenticated"
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs) -> Any:
            session = load_sealed_session(workos_client, cookie_password)
            is_authenticated, reason = authenticate_session(session)

            if is_authenticated:
                log_event("protected_route_access_granted", route=f.__name__)
                return f(*args, **kwargs)

            if reason == "no_session":
                log_event("protected_route_access_denied", route=f.__name__, reason="no_session")
                return make_response(redirect(url_for("auth.login")))

            if session:
                refreshed = refresh_session(session, is_development)
                if refreshed:
                    log_event("session_refreshed", route=f.__name__)
                    return refreshed
                log_event("session_refresh_failed", route=f.__name__)

            log_event("protected_route_access_denied", route=f.__name__, reason=reason)
            response = make_response(redirect(url_for("auth.login")))
            response.delete_cookie("wos_session")
            return response

        return decorated
    return decorator
