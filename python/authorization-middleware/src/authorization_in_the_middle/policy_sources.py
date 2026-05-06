"""Policy bundle sources for Cedar authorization.

Services usually load Cedar policy bundles from their own repository at runtime.
For backwards compatibility and special cases, HTTP fetching remains available as
an optional source.
"""

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import requests


PolicySetDict = dict[str, Any]


class PolicySetSource(Protocol):
    def get_policy_set(self) -> PolicySetDict: ...


def _load_policy_files(policies_dir: Path) -> list[dict[str, str]]:
    cedar_files = sorted(policies_dir.glob("*.cedar"))
    return [
        {"name": policy_file.stem, "content": policy_file.read_text(encoding="utf-8")}
        for policy_file in cedar_files
    ]


def _compute_version(schema_content: str, policies: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    digest.update(schema_content.encode())
    for policy in policies:
        digest.update(policy["name"].encode())
        digest.update(policy["content"].encode())
    return f"sha256:{digest.hexdigest()[:16]}"


def _build_policy_set(policies_dir: Path) -> PolicySetDict:
    schema_path = policies_dir / "schema.cedar.json"
    schema_content = schema_path.read_text(encoding="utf-8")
    policies = _load_policy_files(policies_dir)
    updated_at = datetime.fromtimestamp(
        max(
            schema_path.stat().st_mtime,
            *(
                (policies_dir / f"{policy['name']}.cedar").stat().st_mtime
                for policy in policies
            ),
        ),
        tz=timezone.utc,
    ).isoformat()
    return {
        "version": _compute_version(schema_content, policies),
        "updated_at": updated_at,
        "schema_content": schema_content,
        "policies": policies,
    }


class FilesystemPolicySetSource:
    """Load and cache a service-owned Cedar policy bundle from disk."""

    def __init__(self, policies_dir: str | Path, cache_ttl: int = 60) -> None:
        self._policies_dir = Path(policies_dir)
        self._cache_ttl = cache_ttl
        self._cached: PolicySetDict | None = None
        self._expires_at: float = 0.0

    def get_policy_set(self) -> PolicySetDict:
        now = time.monotonic()
        if self._cached is not None and now < self._expires_at:
            return self._cached

        self._cached = _build_policy_set(self._policies_dir)
        self._expires_at = now + self._cache_ttl
        return self._cached


class StaticPolicySetSource:
    """Return a pre-built policy bundle, useful in tests."""

    def __init__(self, policy_set: PolicySetDict) -> None:
        self._policy_set = policy_set

    def get_policy_set(self) -> PolicySetDict:
        return self._policy_set


class HttpPolicySetSource:
    """Fetch and cache a Cedar policy bundle from a remote HTTP service."""

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

    def get_policy_set(self) -> PolicySetDict:
        now = time.monotonic()

        if self._cached is not None and now < self._expires_at:
            return self._cached

        if self._cached_version is not None:
            version_resp = self._fetch(
                f"{self._base_url}/api/policies/version",
                timeout=self._timeout,
            )
            version_resp.raise_for_status()
            version_data = version_resp.json()

            if version_data["version"] == self._cached_version:
                self._expires_at = now + int(version_data.get("cache_max_age", 60))
                return self._cached  # type: ignore[return-value]

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


PolicySetClient = HttpPolicySetSource