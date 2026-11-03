"""HTTP session for William Hill racing-API calls.

Stdlib urllib over a certifi-backed TLS context, like the Betfair client.
A context manager so cli.py can inject a stub exactly as it does for the
browser-backed scrapers. No retries."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from types import TracebackType
from typing import Type

import certifi

from .api import API_HEADERS


class FetchError(Exception):
    """Raised when a request fails, returns non-2xx, or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


class HttpSession:
    """Context manager holding one certifi-backed opener per scraper run."""

    def __init__(self, *, opener: urllib.request.OpenerDirector | None = None) -> None:
        self._opener = opener

    def __enter__(self) -> "HttpSession":
        if self._opener is None:
            ctx = ssl.create_default_context(cafile=certifi.where())
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx))
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._opener = None

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        """GET `url` and return the parsed JSON.

        Raises FetchError on network failure, HTTP non-2xx, or invalid JSON."""
        if self._opener is None:
            raise RuntimeError("HttpSession not entered")
        req = urllib.request.Request(url, headers=API_HEADERS, method="GET")
        try:
            with self._opener.open(req, timeout=timeout_ms / 1000) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise FetchError(url, f"HTTP {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            raise FetchError(url, str(e)) from e
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise FetchError(url, f"invalid JSON: {e}") from e
