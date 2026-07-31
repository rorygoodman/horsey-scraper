"""Opt-in live test against the real Novibet feed.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration
Skipped by default — it needs network and a Chromium install."""

from __future__ import annotations

import os

import pytest

from novibet_scraper import api
from novibet_scraper.browser import BrowserSession
from novibet_scraper.overview import parse_overview
from novibet_scraper.racecard import parse_racecard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="live network test; set RUN_INTEGRATION=1 to run",
)


@pytest.mark.integration
def test_live_index_and_one_racecard():
    with BrowserSession() as session:
        payload = session.fetch_json(api.OVERVIEW_URL)
        stubs = parse_overview(payload)
        assert stubs, "live day index returned no races"

        gb = [s for s in stubs if s.country in ("GB", "IRE")]
        if not gb:
            pytest.skip("no GB/IRE racing in the live index today")

        race = None
        for stub in gb:
            card = session.fetch_json(api.racecard_url(stub.bet_context_id))
            race = parse_racecard(card, "2026-01-01T00:00:00Z",
                                  venue=stub.venue, country=stub.country)
            if race is not None:
                break
        assert race is not None, "no GB/IRE race had a usable win market"
        assert race.runners
        if race.each_way_terms is not None:
            assert 0.0 < race.each_way_terms.fraction <= 1.0
            assert race.each_way_terms.places >= 1
