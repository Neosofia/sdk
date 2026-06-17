import pytest
from unittest.mock import MagicMock, patch

from platform_client.token_broker import ServiceTokenBroker


@patch("platform_client.token_broker.httpx.post")
def test_token_broker_fetches_audience_scoped_token(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"access_token": "jwt-for-chat"},
    )
    mock_post.return_value.raise_for_status = MagicMock()

    broker = ServiceTokenBroker(
        auth_base_url="http://auth:8014",
        client_id="care-episode",
        client_secret="secret",
    )
    assert broker.get_token("chat") == "jwt-for-chat"
    assert broker.get_token("chat") == "jwt-for-chat"
    mock_post.assert_called_once()
