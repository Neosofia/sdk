"""
WorkOS session management utilities.

Provides reusable functions for loading, authenticating, and refreshing
WorkOS sealed sessions across Neosofia platform services.
"""

from typing import Optional, Tuple

from flask import make_response, redirect, request


def load_sealed_session(workos_client, cookie_password: str):
    """
    Load a sealed session from the wos_session request cookie.

    Returns:
        WorkOS session object, or None if no cookie present or load fails.
    """
    sealed = request.cookies.get("wos_session") or ""
    if not sealed:
        return None

    try:
        return workos_client.user_management.load_sealed_session(
            session_data=sealed,
            cookie_password=cookie_password,
        )
    except Exception:
        return None


def authenticate_session(session) -> Tuple[bool, Optional[str]]:
    """
    Authenticate a loaded WorkOS session.

    Returns:
        (is_authenticated, reason_if_failed) — reason is None on success.
    """
    if not session:
        return False, "no_session"

    try:
        auth_response = session.authenticate()
        if auth_response.authenticated:
            return True, None
        reason = getattr(auth_response, "reason", "unknown")
        return False, reason
    except Exception as e:
        return False, str(e)


def refresh_session(session, is_development: bool):
    """
    Attempt to refresh an expired WorkOS session.

    Returns:
        Flask response with updated cookie on success, or None if refresh fails.
    """
    try:
        result = session.refresh()
        if not result.authenticated:
            return None

        response = make_response(redirect(request.url))
        response.set_cookie(
            "wos_session",
            getattr(result, "sealed_session", ""),
            secure=not is_development,
            httponly=True,
            samesite="lax",
        )
        return response
    except Exception:
        return None


def revoke_session_cookie():
    """
    Create a response that deletes the wos_session cookie.

    Returns:
        Flask response redirecting to / with the session cookie cleared.
    """
    response = make_response(redirect("/"))
    response.delete_cookie("wos_session")
    return response
