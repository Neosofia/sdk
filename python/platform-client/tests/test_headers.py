import pytest

from platform_client.headers import forward_request_headers, outbound_headers


def test_outbound_headers_service_token():
    assert outbound_headers(access_token="jwt") == {"Authorization": "Bearer jwt"}


def test_outbound_headers_forward_from_mapping():
    headers = outbound_headers(
        forward_from={
            "Authorization": "Bearer patient-jwt",
            "X-Active-Actor": " patient ",
            "X-Empty": "   ",
        }
    )
    assert headers == {
        "Authorization": "Bearer patient-jwt",
        "X-Active-Actor": "patient",
    }


def test_forward_request_headers_custom_names():
    headers = forward_request_headers(
        {"Authorization": "Bearer x", "X-Trace-Id": "abc"},
        names=("X-Trace-Id",),
    )
    assert headers == {"X-Trace-Id": "abc"}
