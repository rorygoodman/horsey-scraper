"""Unit tests for the Novibet browser session — no network.

The live path is covered by the opt-in integration test in Task 13."""

from __future__ import annotations

import json

import pytest

from novibet_scraper import api
from novibet_scraper.browser import BrowserFetchError, BrowserSession


class _FakePage:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, js, args):
        self.calls.append((js, args))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _session_with(page) -> BrowserSession:
    s = BrowserSession()
    s._page = page
    return s


def test_fetch_json_parses_the_body():
    page = _FakePage(json.dumps({"days": []}))
    assert _session_with(page).fetch_json("https://x/y") == {"days": []}


def test_fetch_json_sends_the_gateway_headers():
    page = _FakePage(json.dumps({}))
    _session_with(page).fetch_json("https://x/y")
    _js, args = page.calls[0]
    url, headers, timeout = args
    assert url == "https://x/y"
    assert headers == api.API_HEADERS
    assert timeout == 20_000


def test_fetch_json_raises_on_invalid_json():
    page = _FakePage("<html>403</html>")
    with pytest.raises(BrowserFetchError) as e:
        _session_with(page).fetch_json("https://x/y")
    assert "invalid JSON" in e.value.reason


def test_fetch_json_wraps_evaluation_failure():
    page = _FakePage(RuntimeError("HTTP 403: blocked"))
    with pytest.raises(BrowserFetchError) as e:
        _session_with(page).fetch_json("https://x/y")
    assert "403" in e.value.reason


def test_fetch_json_before_enter_is_a_runtime_error():
    with pytest.raises(RuntimeError):
        BrowserSession().fetch_json("https://x/y")


def test_warmup_url_is_novibets_racing_page():
    assert api.WARMUP_URL.startswith("https://www.novibet.ie/")
