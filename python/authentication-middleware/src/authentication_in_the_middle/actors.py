"""Tier-1 actor allow-list: fetched from Authentication well-known metadata."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")


def parse_tier1_actor_classes(valid_actors: str) -> frozenset[str]:
    """Parse comma-separated actor list (tests and explicit Flask config only)."""
    return frozenset(part.strip() for part in valid_actors.split(",") if part.strip())


def platform_actors_uri_from_jwks(jwks_uri: str) -> str:
    """Derive platform-actors URL from the JWKS well-known URL (same directory as jwks.json)."""
    uri = jwks_uri.strip()
    if uri.endswith("/jwks.json"):
        return f"{uri[:-len('/jwks.json')]}/platform-actors.json"
    if uri.endswith("jwks.json"):
        return f"{uri[:-len('jwks.json')]}platform-actors.json"
    return f"{uri.rstrip('/')}/.well-known/platform-actors.json"


@lru_cache(maxsize=8)
def fetch_tier1_actor_classes(jwks_uri: str) -> frozenset[str]:
    """Fetch and cache Tier-1 actors published by Authentication (Cache-Control honoured by TTL here)."""
    actors_uri = platform_actors_uri_from_jwks(jwks_uri)
    request = Request(actors_uri, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Failed to load platform actors from {actors_uri}") from exc

    raw = payload.get("tier1_actors")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"platform-actors document at {actors_uri} missing non-empty tier1_actors")

    actors: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str) or not _SLUG.match(entry) or entry in seen:
            raise RuntimeError(f"Invalid tier1_actors entry in {actors_uri}")
        seen.add(entry)
        actors.append(entry)
    return frozenset(actors)


def ensure_tier1_actor_classes(app) -> frozenset[str]:
    """Load and cache ``TIER1_ACTOR_CLASSES`` from platform-actors.json (requires ``JWT_JWKS_URI``)."""
    existing = app.config.get("TIER1_ACTOR_CLASSES")
    if isinstance(existing, frozenset):
        return existing
    jwks_uri = app.config.get("JWT_JWKS_URI")
    if not jwks_uri:
        empty: frozenset[str] = frozenset()
        app.config["TIER1_ACTOR_CLASSES"] = empty
        return empty
    classes = fetch_tier1_actor_classes(str(jwks_uri))
    app.config["TIER1_ACTOR_CLASSES"] = classes
    return classes


def configure_tier1_actor_classes(app) -> None:
    """
    Eagerly set ``TIER1_ACTOR_CLASSES`` at startup when ``JWT_JWKS_URI`` is configured.

    Uses the same origin as JWKS: ``/.well-known/platform-actors.json``.
    In ``ENV=test``, fetch failures are deferred to the first authenticated request.
    """
    if app.config.get("TIER1_ACTOR_CLASSES") is not None:
        return
    jwks_uri = app.config.get("JWT_JWKS_URI")
    if not jwks_uri:
        return
    try:
        ensure_tier1_actor_classes(app)
    except RuntimeError:
        env = str(app.config.get("ENV", "")).lower()
        if env not in ("test", "testing"):
            raise
