from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from platform_client.token_broker import ServiceTokenBroker

REGISTRY_TOKEN_AUDIENCE = "authentication"


class ServiceNotRegisteredError(Exception):
    """Authentication registry has no service with the requested slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"service not registered: {slug}")
        self.slug = slug


class RegistryUnavailableError(Exception):
    """Registry lookup failed due to network, upstream, or malformed response."""


@dataclass
class ServiceRegistryClient:
    """Resolve peer service base URLs via Authentication ``GET /api/services/{slug}``."""

    auth_base_url: str
    token_broker: ServiceTokenBroker
    cache_ttl_seconds: float = 60.0
    timeout_seconds: float = 10.0
    _cache: dict[str, tuple[str, float]] = field(default_factory=dict, repr=False)

    def resolve_base_url(self, slug: str) -> str:
        normalized_slug = slug.strip()
        if not normalized_slug:
            raise RegistryUnavailableError("service slug is required")

        cached = self._read_cached(normalized_slug)
        if cached is not None:
            return cached

        base = self.auth_base_url.strip().rstrip("/")
        if not base:
            raise RegistryUnavailableError("authentication service is not configured")

        try:
            token = self.token_broker.get_token(REGISTRY_TOKEN_AUDIENCE)
            response = httpx.get(
                f"{base}/api/services/{normalized_slug}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise RegistryUnavailableError("authentication service is temporarily unavailable") from exc

        if response.status_code == 404:
            raise ServiceNotRegisteredError(normalized_slug)
        if not response.is_success:
            raise RegistryUnavailableError("failed to resolve service base url")

        try:
            body = response.json()
        except ValueError as exc:
            raise RegistryUnavailableError("service registry returned invalid json") from exc

        if not isinstance(body, dict):
            raise RegistryUnavailableError("service registry returned invalid response")

        base_url = str(body.get("base_url") or "").strip()
        if not base_url:
            raise RegistryUnavailableError("service registry returned empty base_url")

        self._write_cache(normalized_slug, base_url)
        return base_url

    def _read_cached(self, slug: str) -> str | None:
        entry = self._cache.get(slug)
        if entry is None:
            return None
        base_url, expires_at = entry
        if time.monotonic() >= expires_at:
            self._cache.pop(slug, None)
            return None
        return base_url

    def _write_cache(self, slug: str, base_url: str) -> None:
        self._cache[slug] = (base_url, time.monotonic() + self.cache_ttl_seconds)
