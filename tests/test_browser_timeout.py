"""Offline unit tests for the in-page fetch timeout wiring, shared by both
browser modules (paddypower_scraper.browser, sport888_scraper.browser).

No real browser: a FakePage records the args passed to page.evaluate. These
lock the fix that makes `timeout_ms` actually bound the in-page fetch (it used
to be a dead parameter — an unresponsive endpoint could hang indefinitely)."""

import pytest

import paddypower_scraper.browser as paddy_browser
import sport888_scraper.browser as sport888_browser

BROWSER_MODULES = [paddy_browser, sport888_browser]


class FakePage:
    """Stand-in for a Playwright Page: records evaluate() args, returns a
    canned body (or raises), so fetch_json can be exercised without a browser."""

    def __init__(self, result: str = '{"ok": true}', exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls: list[tuple] = []

    def evaluate(self, js, arg):
        self.calls.append((js, arg))
        if self.exc is not None:
            raise self.exc
        return self.result


@pytest.mark.parametrize("mod", BROWSER_MODULES, ids=lambda m: m.__name__)
def test_fetch_json_forwards_timeout_ms_to_page(mod):
    session = mod.BrowserSession()
    page = FakePage(result='{"ok": true}')
    session._page = page
    data = session.fetch_json("https://x/api", timeout_ms=5000)
    assert data == {"ok": True}
    js, arg = page.calls[0]
    # url + timeout must be passed together so timeout_ms actually reaches the page
    assert isinstance(arg, (list, tuple)), f"expected [url, timeout], got {arg!r}"
    assert "https://x/api" in arg
    assert 5000 in arg
    # and the page-side code must actually enforce it (abort the fetch on timeout)
    assert "AbortController" in js
    assert "signal" in js


@pytest.mark.parametrize("mod", BROWSER_MODULES, ids=lambda m: m.__name__)
def test_fetch_json_wraps_evaluate_error(mod):
    session = mod.BrowserSession()
    session._page = FakePage(exc=RuntimeError("boom"))
    with pytest.raises(mod.BrowserFetchError):
        session.fetch_json("https://x/api")


@pytest.mark.parametrize("mod", BROWSER_MODULES, ids=lambda m: m.__name__)
def test_fetch_json_before_enter_raises_runtimeerror(mod):
    session = mod.BrowserSession()
    with pytest.raises(RuntimeError):
        session.fetch_json("https://x/api")
