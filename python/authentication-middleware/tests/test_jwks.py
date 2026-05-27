from unittest.mock import patch

from authentication_in_the_middle.jwks import get_jwks_client


def test_get_jwks_client_is_cached_per_uri():
    get_jwks_client.cache_clear()

    with patch("authentication_in_the_middle.jwks.pyjwt.PyJWKClient") as mock_client:
        mock_client.side_effect = [object(), object()]

        first = get_jwks_client("https://auth.example/.well-known/jwks.json")
        second = get_jwks_client("https://auth.example/.well-known/jwks.json")
        other = get_jwks_client("https://other.example/.well-known/jwks.json")

    assert first is second
    assert first is not other
    assert mock_client.call_count == 2
