"""Tests for betfair_scraper.race_list."""

from __future__ import annotations

import json
from datetime import date

from betfair_scraper.race_list import (
    RaceListFetcher,
    london_day_window_utc,
    parse_catalogue_races,
)


class TestLondonDayWindowUtc:
    def test_bst(self):
        # May → BST (+01:00): day starts 23:00Z the previous date.
        assert london_day_window_utc(date(2026, 5, 11)) == (
            "2026-05-10T23:00:00Z", "2026-05-11T23:00:00Z")

    def test_gmt(self):
        assert london_day_window_utc(date(2026, 1, 15)) == (
            "2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z")


def _cat(*entries) -> str:
    return json.dumps(list(entries))


def _entry(market_id, start_utc, venue, country):
    return {"marketId": market_id, "marketStartTime": start_utc,
            "event": {"venue": venue, "countryCode": country}}


class TestParseCatalogueRaces:
    def test_dedupe_and_sort(self):
        text = _cat(
            _entry("1.2", "2026-05-25T18:00:00Z", "Zborough", "GB"),
            _entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"),
            _entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"),  # dup
        )
        races = parse_catalogue_races(text)
        assert [r.race_id for r in races] == ["1.1", "1.2"]  # sorted by offTime

    def test_skips_unparseable(self):
        text = _cat(
            {"marketId": "1.1"},  # missing fields
            _entry("1.2", "2026-05-25T18:00:00Z", "Ascot", "GB"),
        )
        assert [r.race_id for r in parse_catalogue_races(text)] == ["1.2"]


class FakeClient:
    def __init__(self, catalogue_response: str):
        self.catalogue_response = catalogue_response
        self.last_body = None

    def list_market_catalogue(self, body: str) -> str:
        self.last_body = body
        return self.catalogue_response

    def list_market_book(self, body: str) -> str:  # unused here
        raise AssertionError("not called")


class TestRaceListFetcher:
    def test_fetch_uses_win_and_countries(self):
        resp = _cat(_entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"))
        client = FakeClient(resp)
        races = RaceListFetcher(client).fetch(
            frozenset({"gb-ie"}), today=date(2026, 5, 25))
        assert [r.race_id for r in races] == ["1.1"]
        body = json.loads(client.last_body)
        assert body["filter"]["marketTypeCodes"] == ["WIN"]
        assert body["filter"]["marketCountries"] == ["GB", "IE"]
