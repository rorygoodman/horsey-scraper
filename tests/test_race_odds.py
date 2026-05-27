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


def test_parse_catalogue_place_markets_routes_by_market_type():
    text = json.dumps([
        {  # explicit OTHER_PLACE → TOP_2
            "marketName": "2 TBP", "marketId": "9.1",
            "description": {"marketType": "OTHER_PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # standard PLACE → deferred (type None), kept
            "marketName": "To Be Placed", "marketId": "9.2",
            "description": {"marketType": "PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # OTHER_PLACE that doesn't classify → dropped
            "marketName": "Without Fav", "marketId": "9.3",
            "description": {"marketType": "OTHER_PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"}, "runners": [],
        },
    ])
    by_id = {e.market_id: e for e in parse_catalogue_place_markets(text)}
    assert set(by_id) == {"9.1", "9.2"}
    assert by_id["9.1"].type is MarketType.TOP_2
    assert by_id["9.2"].type is None          # deferred standard place market
    assert by_id["9.2"].runners == {1: "A"}


def test_parse_catalogue_place_markets_name_fallback_without_market_type():
    # No description.marketType → fall back to name matching.
    text = json.dumps([
        {"marketName": "To Be Placed", "marketId": "9.1",
         "description": {"marketTime": "2026-05-25T17:00:00Z"},
         "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}]},
        {"marketName": "2 TBP", "marketId": "9.2",
         "description": {"marketTime": "2026-05-25T17:00:00Z"},
         "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}]},
    ])
    by_id = {e.market_id: e for e in parse_catalogue_place_markets(text)}
    assert by_id["9.1"].type is None          # "To Be Placed" → deferred
    assert by_id["9.2"].type is MarketType.TOP_2


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


def test_fetcher_resolves_to_be_placed_to_top_n():
    # Integration: a marketType=="PLACE" "To Be Placed" market flows through
    # the full fetch → bind → book → resolve pipeline and becomes a TOP_N
    # (N from the book's numberOfWinners), not just at the join_scrapes unit.
    win_json = json.dumps([{
        "marketId": "1.1", "marketName": "2m Hcap",
        "marketStartTime": "2026-05-25T17:00:00Z", "event": {"id": "30.1"},
        "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    place_json = json.dumps([{
        "marketName": "To Be Placed", "marketId": "9.tbp",
        "description": {"marketType": "PLACE", "marketTime": "2026-05-25T17:00:00Z"},
        "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    book_json = json.dumps([
        {"marketId": "1.1", "status": "OPEN",
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}]},
        {"marketId": "9.tbp", "status": "OPEN", "numberOfWinners": 3,
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 1.6}]}}]},
    ])
    client = FakeClient(win_json, place_json, book_json)
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    out = RaceOddsFetcher(
        client, now=lambda: __import__("datetime").datetime(
            2026, 5, 25, 17, 0, tzinfo=__import__("datetime").timezone.utc)
    ).fetch(races, frozenset({"gb-ie"}))
    assert len(out) == 1
    assert list(out[0].market_scraped_at) == [MarketType.WIN, MarketType.TOP_3]
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_3: 1.6}


def test_join_scrapes_resolves_to_be_placed_from_book():
    races = [Race("1.1", "Kempton", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"})]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.6}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert list(out[0].market_scraped_at) == [MarketType.WIN, MarketType.TOP_3]
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_3: 1.6}


def test_join_scrapes_to_be_placed_count_out_of_range_dropped():
    races = [Race("1.1", "X", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"})]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.6}, number_of_winners=1),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert list(out[0].market_scraped_at) == [MarketType.WIN]  # 1 place → no TOP_N


def test_join_scrapes_merges_contested_topn_per_runner_best():
    races = [Race("1.1", "X", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [
        PlaceMarketEntry("9.explicit", MarketType.TOP_3, "30.1", "t", {1: "A", 2: "B"}),
        PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A", 2: "B"}),
    ]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5, 2: 2.5}),
        "9.explicit": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.60, 2: 5.20}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.45, 2: 5.40}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A"), (2, "B")]}, "n", "t")
    lays = {r.name: r.lay[MarketType.TOP_3] for r in out[0].runners}
    assert lays == {"A": 3.45, "B": 5.20}  # per-runner cheapest across the two books


def test_join_scrapes_kempton_shape():
    # Live Kempton 21:00 shape: explicit 2 TBP + 4 TBP, plus To-Be-Placed paying 3.
    races = [Race("1.1", "Kempton", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [
        PlaceMarketEntry("9.2", MarketType.TOP_2, "30.1", "t", {1: "A"}),
        PlaceMarketEntry("9.4", MarketType.TOP_4, "30.1", "t", {1: "A"}),
        PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"}),
    ]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.2": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.8}),
        "9.4": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.8}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.3}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert set(out[0].market_scraped_at) == {
        MarketType.WIN, MarketType.TOP_2, MarketType.TOP_3, MarketType.TOP_4}
    assert out[0].runners[0].lay[MarketType.TOP_3] == 2.3
