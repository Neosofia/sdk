from __future__ import annotations

from collections.abc import Mapping

# Headers a BFF/proxy forwards so downstream services see the same caller identity
# and active actor (see authentication-in-the-middle X-Active-Actor handling).
FORWARDED_REQUEST_HEADERS = ("Authorization", "X-Active-Actor")


def forward_request_headers(
    incoming: Mapping[str, str | None],
    *,
    names: tuple[str, ...] = FORWARDED_REQUEST_HEADERS,
) -> dict[str, str]:
    """Copy platform proxy headers from an inbound request mapping."""
    forwarded: dict[str, str] = {}
    for name in names:
        value = incoming.get(name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            forwarded[name] = stripped
    return forwarded


def outbound_headers(
    *,
    access_token: str | None = None,
    forward_from: Mapping[str, str | None] | None = None,
    forward_names: tuple[str, ...] = FORWARDED_REQUEST_HEADERS,
) -> dict[str, str]:
    """Build outbound Authorization headers for platform service calls.

    Pass ``access_token`` for service-to-service calls (caller mints the JWT).
    Pass ``forward_from`` (e.g. ``request.headers``) when proxying the current
    caller's credentials to a downstream service without token exchange.
    """
    if access_token is not None:
        return {"Authorization": f"Bearer {access_token}"}
    if forward_from is not None:
        return forward_request_headers(forward_from, names=forward_names)
    return {}
