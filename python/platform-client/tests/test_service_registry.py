from unittest.mock import MagicMock, patch

import httpx
import pytest

from platform_client.service_registry import (
    RegistryUnavailableError,
    ServiceNotRegisteredError,
    ServiceRegistryClient,
)
from platform_client.token_broker import ServiceTokenBroker


@pytest.fixture
def broker():
    return ServiceTokenBroker(
        auth_base_url="http://auth:8014",
        client_id="care-episode",
        client_secret="secret",
    )


@pytest.fixture
def registry(broker):
    return ServiceRegistryClient(
        auth_base_url="http://auth:8014",
        token_broker=broker,
        cache_ttl_seconds=60.0,
        timeout_seconds=5.0,
    )


@patch("platform_client.service_registry.httpx.get")
def test_resolve_base_url_success(mock_get, registry, broker):
    mock_get.return_value = MagicMock(
        status_code=200,
        is_success=True,
        json=lambda: {"slug": "chat", "base_url": "http://chat:8001"},
    )
    with patch.object(broker, "get_token", return_value="registry-token") as mock_token:
        assert registry.resolve_base_url("chat") == "http://chat:8001"
        mock_token.assert_called_once_with("authentication")
        mock_get.assert_called_once_with(
            "http://auth:8014/api/services/chat",
            headers={"Authorization": "Bearer registry-token"},
            timeout=5.0,
        )

        mock_get.reset_mock()
        assert registry.resolve_base_url("chat") == "http://chat:8001"
        mock_get.assert_not_called()


@patch("platform_client.service_registry.httpx.get")
def test_resolve_base_url_not_registered(mock_get, registry, broker):
    mock_get.return_value = MagicMock(status_code=404, is_success=False)
    with patch.object(broker, "get_token", return_value="registry-token"):
        with pytest.raises(ServiceNotRegisteredError, match="chat"):
            registry.resolve_base_url("chat")


@patch("platform_client.service_registry.httpx.get")
def test_resolve_base_url_network_error(mock_get, registry, broker):
    mock_get.side_effect = httpx.ConnectError("connection refused")
    with patch.object(broker, "get_token", return_value="registry-token"):
        with pytest.raises(RegistryUnavailableError, match="temporarily unavailable"):
            registry.resolve_base_url("chat")


@patch("platform_client.service_registry.httpx.get")
def test_resolve_base_url_empty_base_url(mock_get, registry, broker):
    mock_get.return_value = MagicMock(
        status_code=200,
        is_success=True,
        json=lambda: {"slug": "chat", "base_url": "  "},
    )
    with patch.object(broker, "get_token", return_value="registry-token"):
        with pytest.raises(RegistryUnavailableError, match="empty base_url"):
            registry.resolve_base_url("chat")


def test_resolve_base_url_requires_slug(registry):
    with pytest.raises(RegistryUnavailableError, match="slug is required"):
        registry.resolve_base_url("   ")
