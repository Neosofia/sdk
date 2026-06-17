from __future__ import annotations

import httpx


class UpstreamError(Exception):
    """Downstream returned a 4xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UpstreamUnavailable(Exception):
    """Downstream returned 5xx."""


def response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("error") or body.get("message") or body.get("detail")
            if detail is not None:
                return str(detail)
    except ValueError:
        pass
    text = response.text.strip()
    if text:
        return text
    return response.reason_phrase or "request failed"


def raise_for_upstream_response(response: httpx.Response) -> None:
    """Raise if the downstream response is not successful.

    5xx → ``UpstreamUnavailable``. 4xx → ``UpstreamError`` with status and detail.
    """
    if response.is_success:
        return
    detail = response_detail(response)
    if response.status_code >= 500:
        raise UpstreamUnavailable(detail)
    raise UpstreamError(response.status_code, detail)
