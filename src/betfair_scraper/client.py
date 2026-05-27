"""Thin REST client for the three Betfair endpoints. Port of BetfairClient.kt.
Uses stdlib urllib (no browser, no third-party dep). No retries."""

from __future__ import annotations

import urllib.error
import urllib.request

from .responses import build_login_body, parse_ssoid

LOGIN_URL = "https://identitysso.betfair.com/api/login"
CATALOGUE_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/"
BOOK_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/"


class BetfairClient:
    def __init__(self, app_key: str, *, opener=None):
        self.app_key = app_key
        self._ssoid: "str | None" = None
        self._opener = opener or urllib.request.build_opener()

    def login(self, username: str, password: str) -> None:
        req = urllib.request.Request(
            LOGIN_URL,
            data=build_login_body(username, password).encode(),
            headers={
                "X-Application": self.app_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        self._ssoid = parse_ssoid(self._send(req, timeout=15))

    def list_market_catalogue(self, body: str) -> str:
        return self._send(self._betting_request(CATALOGUE_URL, body), timeout=30)

    def list_market_book(self, body: str) -> str:
        return self._send(self._betting_request(BOOK_URL, body), timeout=30)

    def _betting_request(self, url: str, body: str) -> urllib.request.Request:
        if self._ssoid is None:
            raise RuntimeError("BetfairClient: must call login() before betting endpoints")
        return urllib.request.Request(
            url,
            data=body.encode(),
            headers={
                "X-Application": self.app_key,
                "X-Authentication": self._ssoid,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def _send(self, req: urllib.request.Request, timeout: int) -> str:
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            snippet = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"HTTP {e.code} from {req.full_url}: {snippet}")
