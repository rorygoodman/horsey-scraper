import io
import urllib.error

import pytest

from williamhill_scraper.client import FetchError, HttpSession


class _Opener:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def open(self, req, timeout):
        self.requests.append(req)
        if isinstance(self.result, Exception):
            raise self.result
        return io.BytesIO(self.result)


def test_returns_parsed_json_and_sends_headers():
    op = _Opener(b'{"ok": true}')
    with HttpSession(opener=op) as s:
        assert s.fetch_json("https://x/y") == {"ok": True}
    assert op.requests[0].get_header("Accept") == "application/json"
    assert "Mozilla" in op.requests[0].get_header("User-agent")


def test_http_error_raises_fetch_error():
    err = urllib.error.HTTPError("https://x/y", 503, "busy", {}, None)
    with HttpSession(opener=_Opener(err)) as s:
        with pytest.raises(FetchError) as ei:
            s.fetch_json("https://x/y")
    assert ei.value.reason == "HTTP 503"


def test_network_error_raises_fetch_error():
    with HttpSession(opener=_Opener(urllib.error.URLError("dns"))) as s:
        with pytest.raises(FetchError):
            s.fetch_json("https://x/y")


def test_invalid_json_raises_fetch_error():
    with HttpSession(opener=_Opener(b"<html>")) as s:
        with pytest.raises(FetchError) as ei:
            s.fetch_json("https://x/y")
    assert ei.value.reason.startswith("invalid JSON")


def test_unentered_session_raises():
    with pytest.raises(RuntimeError):
        HttpSession().fetch_json("https://x/y")
