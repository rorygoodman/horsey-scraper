"""Tests for betfair_scraper.client. The HTTP path is opt-in (real creds)."""

from __future__ import annotations

import os

import pytest

from betfair_scraper.client import BetfairClient


def test_betting_endpoint_requires_login():
    client = BetfairClient("app-key")
    with pytest.raises(RuntimeError, match="must call login"):
        client.list_market_catalogue("{}")


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                    reason="set RUN_INTEGRATION=1 (needs ~/.horsey-scraper/credentials.json)")
def test_live_login_and_catalogue():
    from betfair_scraper.credentials import default_credentials_path, load_credentials
    from betfair_scraper.race_list import RaceListFetcher

    creds = load_credentials(default_credentials_path())
    client = BetfairClient(creds.app_key)
    client.login(creds.username, creds.password)
    races = RaceListFetcher(client).fetch(frozenset({"gb-ie"}))
    assert isinstance(races, list)
