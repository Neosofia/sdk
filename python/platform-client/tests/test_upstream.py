from unittest.mock import MagicMock

import pytest

from platform_client.upstream import UpstreamError, UpstreamUnavailable, raise_for_upstream_response, response_detail


def test_response_detail_prefers_json_error_field():
    response = MagicMock()
    response.json.return_value = {"error": "forbidden"}
    response.text = ""
    response.reason_phrase = "Forbidden"
    assert response_detail(response) == "forbidden"


def test_raise_for_upstream_response_maps_503_to_unavailable():
    response = MagicMock()
    response.is_success = False
    response.status_code = 503
    response.json.side_effect = ValueError("not json")
    response.text = ""
    response.reason_phrase = "Service Unavailable"

    with pytest.raises(UpstreamUnavailable):
        raise_for_upstream_response(response)


def test_raise_for_upstream_response_maps_403_to_upstream_error():
    response = MagicMock()
    response.is_success = False
    response.status_code = 403
    response.json.return_value = {"error": "forbidden"}
    response.text = ""
    response.reason_phrase = "Forbidden"

    with pytest.raises(UpstreamError) as exc_info:
        raise_for_upstream_response(response)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "forbidden"
