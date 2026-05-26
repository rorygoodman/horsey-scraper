"""Tests for betfair_scraper.race_odds."""

from __future__ import annotations

import json

from common.markettype import MarketType
from betfair_scraper.models import Race
from betfair_scraper.race_odds import (
    PlaceMarketEntry,
    RaceOddsFetcher,
    chunk_of_40,
    join_scrapes,
    parse_book_snapshots,
    parse_catalogue_place_markets,
    parse_win_catalogue_runners,
    parse_win_race_keys,
    parse_win_race_types,
    place_markets_by_race_id,
)
from betfair_scraper.responses import MarketBookSnapshot, MarketBookStatus


def test_chunk_of_40():
    assert chunk_of_40([]) == []
    assert chunk_of_40(list(range(41))) == [list(range(40)), [40]]


def test_parse_catalogue_place_markets_filters_and_binds():
    text = json.dumps([
        {  # a Top-2 market that classifies
            "marketName": "2 TBP",
            "marketId": "9.1",
            "description": {"marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # To Be Placed → rejected by classifier
            "marketName": "To Be Placed",
            "marketId": "9.2",
            "description": {"marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [],
        },
    ])
    entries = parse_catalogue_place_markets(text)
    assert len(entries) == 1
    assert entries[0].market_id == "9.1"
    assert entries[0].type is MarketType.TOP_2
    assert entries[0].event_id == "30.1"
    assert entries[0].runners == {1: "A"}


def test_place_markets_by_race_id_binds_via_event_and_time():
    entry = PlaceMarketEntry("9.1", MarketType.TOP_2, "30.1",
                             "2026-05-25T17:00:00Z", {1: "A"})
    race_key = {"1.1": ("30.1", "2026-05-25T17:00:00Z")}
    out = place_markets_by_race_id([entry], race_key)
    assert out == {"1.1": [entry]}


def test_parse_win_helpers():
    text = json.dumps([{
        "marketId": "1.1", "marketName": "2m1f Beg Chs",
        "marketStartTime": "2026-05-25T17:00:00Z",
        "event": {"id": "30.1"},
        "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    assert parse_win_catalogue_runners(text) == {"1.1": [(1, "A")]}
    assert parse_win_race_types(text) == {"1.1": "2m1f Beg Chs"}
    assert parse_win_race_keys(text) == {"1.1": ("30.1", "2026-05-25T17:00:00Z")}


def test_join_scrapes_drops_non_open_win():
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    snapshots = {"1.1": MarketBookSnapshot(MarketBookStatus.OTHER, {})}
    out = join_scrapes(races, {}, snapshots, {"1.1": [(1, "A")]}, "name",
                       "2026-05-25T17:00:00Z")
    assert out == []


def test_join_scrapes_builds_win_plus_topn():
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.4}),
    }
    place = {"1.1": [PlaceMarketEntry("9.1", MarketType.TOP_2, "30.1",
                                      "2026-05-25T17:00:00Z", {1: "A"})]}
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "name",
                       "2026-05-25T17:00:00Z")
    assert len(out) == 1
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_2: 1.4}


def test_join_scrapes_win_only_no_place_markets():
    """Kotlin: joinScrapes builds WIN-only RaceOdds when no place markets present."""
    races = [Race("1.1", "Lingfield", "GB", "2026-05-09T13:30:00+01:00", "u")]
    snapshots = {"1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {100: 4.8, 200: None})}
    out = join_scrapes(
        races, {}, snapshots,
        {"1.1": [(100, "Some Horse"), (200, "Outsider Bob")]},
        "13:30 Lingfield", "2026-05-09T12:00:00Z",
    )
    assert len(out) == 1
    assert set(out[0].market_scraped_at.keys()) == {MarketType.WIN}
    names = [r.name for r in out[0].runners]
    assert names == ["Some Horse", "Outsider Bob"]
    assert out[0].runners[0].lay == {MarketType.WIN: 4.8}


def test_join_scrapes_drops_topn_with_non_open_book():
    """Kotlin: joinScrapes drops a TOP_N market whose book is OTHER; race still included."""
    races = [Race("1.1", "Lingfield", "GB", "2026-05-09T13:30:00+01:00", "u")]
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {100: 4.8}),
        "9.1": MarketBookSnapshot(MarketBookStatus.OTHER, {}),
    }
    place = {"1.1": [PlaceMarketEntry("9.1", MarketType.TOP_2, "EVT",
                                      "2026-05-09T12:30:00Z", {100: "Some Horse"})]}
    out = join_scrapes(races, place, snapshots, {"1.1": [(100, "Some Horse")]},
                       "13:30 Lingfield", "2026-05-09T12:00:00Z")
    assert len(out) == 1
    assert set(out[0].market_scraped_at.keys()) == {MarketType.WIN}
    # TOP_2 not present in the lay dict at all
    assert MarketType.TOP_2 not in out[0].runners[0].lay


class FakeClient:
    """Returns catalogue responses by marketTypeCodes, book responses by call."""
    def __init__(self, win_json, place_json, book_json):
        self.win_json, self.place_json, self.book_json = win_json, place_json, book_json
        self.book_calls = 0

    def list_market_catalogue(self, body: str) -> str:
        codes = json.loads(body)["filter"]["marketTypeCodes"]
        return self.win_json if codes == ["WIN"] else self.place_json

    def list_market_book(self, body: str) -> str:
        self.book_calls += 1
        return self.book_json


def test_fetcher_end_to_end():
    win_json = json.dumps([{
        "marketId": "1.1", "marketName": "2m Hcap",
        "marketStartTime": "2026-05-25T17:00:00Z", "event": {"id": "30.1"},
        "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    place_json = json.dumps([{
        "marketName": "2 TBP", "marketId": "9.1",
        "description": {"marketTime": "2026-05-25T17:00:00Z"},
        "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    book_json = json.dumps([
        {"marketId": "1.1", "status": "OPEN",
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}]},
        {"marketId": "9.1", "status": "OPEN",
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 1.4}]}}]},
    ])
    client = FakeClient(win_json, place_json, book_json)
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    out = RaceOddsFetcher(
        client, now=lambda: __import__("datetime").datetime(
            2026, 5, 25, 17, 0, tzinfo=__import__("datetime").timezone.utc)
    ).fetch(races, frozenset({"gb-ie"}))
    assert len(out) == 1
    assert out[0].market_name.startswith("18:00 Ascot")
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_2: 1.4}
    assert client.book_calls == 1  # 2 market ids → exactly one ≤40 chunk
