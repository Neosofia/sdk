from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class ServiceTokenBroker:
    """Fetch and cache audience-scoped platform JWTs via Authentication client_credentials."""

    auth_base_url: str
    client_id: str
    client_secret: str
    timeout_seconds: float = 5.0
    _cache: dict[str, tuple[str, float]] = field(default_factory=dict, repr=False)

    def get_token(self, audience: str) -> str:
        normalized_audience = audience.strip()
        if not normalized_audience:
            raise ValueError("audience is required")

        cached = self._cache.get(normalized_audience)
        if cached is not None:
            token, expires_at = cached
            if time.monotonic() < expires_at:
                return token
            self._cache.pop(normalized_audience, None)

        token = self._fetch_token(normalized_audience)
        # Service tokens are short-lived; cache slightly under the default 300s TTL.
        self._cache[normalized_audience] = (token, time.monotonic() + 240.0)
        return token

    def _fetch_token(self, audience: str) -> str:
        base = self.auth_base_url.strip().rstrip("/")
        secret = self.client_secret.strip()
        if not base or not self.client_id.strip() or not secret:
            raise RuntimeError("authentication client credentials are not configured")

        credentials = base64.b64encode(f"{self.client_id}:{secret}".encode()).decode()
        response = httpx.post(
            f"{base}/api/token",
            data={"grant_type": "client_credentials", "audience": audience},
            headers={"Authorization": f"Basic {credentials}"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("authentication service returned no access_token")
        return token
