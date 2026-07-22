import pytest

from sport888_scraper.browser import BrowserFetchError, BrowserSession


def test_fetch_before_enter_raises():
    session = BrowserSession()
    with pytest.raises(RuntimeError):
        session.fetch_json("https://example.com")


def test_browser_fetch_error_carries_reason():
    e = BrowserFetchError("https://x", "HTTP 500")
    assert e.url == "https://x"
    assert e.reason == "HTTP 500"
