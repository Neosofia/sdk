"""
PolicySetClient — fetches and caches the Cedar policy set from the Authorization Service.

The client uses a two-step refresh strategy that matches the OPAL polling model:
  1. Poll GET /api/policies/version (cheap — just a hash + TTL).
  2. Only fetch GET /api/policies (full payload) when the version hash has changed.

Cache TTL is always sourced from the service-provided X-Authorization-Cache-Expiry header;
the client never applies its own assumptions.
"""

import time
from typing import Any, Callable

import requests


# Type alias for the raw policy-set dict returned by GET /api/policies.
PolicySetDict = dict[str, Any]


class PolicySetClient:
    """
    Thread-safe* policy-set cache for the Neosofia Authorization Service.

    *Concurrent refreshes are safe but may result in redundant fetches under
    high contention. For the prototype this is acceptable; add a lock if needed.

    Args:
        base_url:   Base URL of the Authorization Service, e.g. "http://authorization:8006".
        timeout:    HTTP request timeout in seconds.
        fetch_fn:   Optional replacement for requests.get — useful in tests to
                    inject a Flask test-client adapter.  Must accept (url, timeout=N)
                    and return an object with .json() and .headers.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 5,
        fetch_fn: Callable | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._fetch = fetch_fn or requests.get

        self._cached: PolicySetDict | None = None
        self._cached_version: str | None = None
        self._expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_policy_set(self) -> PolicySetDict:
        """
        Return the current policy set, refreshing from the service when stale.

        Raises:
            requests.HTTPError: if the Authorization Service returns a non-2xx response.
            requests.ConnectionError: if the service is unreachable.
        """
        now = time.monotonic()

        if self._cached is not None and now < self._expires_at:
            return self._cached

        if self._cached_version is not None:
            # Cheap version check before committing to a full fetch.
            version_resp = self._fetch(
                f"{self._base_url}/api/policies/version",
                timeout=self._timeout,
            )
            version_resp.raise_for_status()
            version_data = version_resp.json()

            if version_data["version"] == self._cached_version:
                # Policies unchanged — extend TTL and return cached copy.
                self._expires_at = now + int(version_data.get("cache_max_age", 60))
                return self._cached  # type: ignore[return-value]

        return self._full_fetch(now)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _full_fetch(self, now: float) -> PolicySetDict:
        resp = self._fetch(
            f"{self._base_url}/api/policies",
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data: PolicySetDict = resp.json()
        cache_max_age = int(resp.headers.get("X-Authorization-Cache-Expiry", 60))

        self._cached = data
        self._cached_version = data["version"]
        self._expires_at = now + cache_max_age
        return data
