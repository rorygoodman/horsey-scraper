from __future__ import annotations

from dataclasses import replace

import pytest

from common.markettype import MarketType
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from arb_finder.calculator import find_horses_by_name


def _betfair(win_lay=2.0, place_lay=1.4, venue="Worcester",
             off="2026-07-22T13:55:00+01:00", runner_name="Holy Legend") -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-07-22T12:00:00Z", race_count=1,
        races=[RaceOdds(
            race_id="1.1", venue=venue, country="GB", off_time=off,
            win_market_url="u", market_name="12:55 Worcester",
            market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z",
                               MarketType.TOP_3: "2026-07-22T12:00:00Z"},
            runners=[RunnerOdds(runner_name,
                                {MarketType.WIN: win_lay, MarketType.TOP_3: place_lay},
                                selection_id=99)])],
    )


def _eight88(runner_name="Holy Legend", venue="Worcester",
             off="2026-07-22T12:55:00+00:00", places=3) -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:30Z", race_count=1,
        races=[Sport888Race(
            venue=venue, country="uk-and-ireland", off_time=off,
            market_name="Winner Market", scraped_at="2026-07-22T12:00:30Z",
            each_way_terms=EachWayTerms(fraction=0.2, places=places),
            runners=[Sport888Runner(runner_name, 3.0, "2/1")])],
    )


def test_matched_runner_priced():
    horses, stats = find_horses_by_name(_betfair(2.0, 1.4), _eight88())
    assert len(horses) == 1
    h = horses[0]
    assert h.runner.selection_id == 99          # from matched Betfair runner
    assert h.runner.name == "Holy Legend"
    assert h.country == "GB"                     # from matched Betfair race
    assert h.betfair_win_market_id == "1.1"
    assert h.betfair.place_market is MarketType.TOP_3
    assert h.bookie.win_price == 3.0
    assert h.edge == pytest.approx(0.25)
    assert stats.races_matched == 1
    assert stats.runners_priced == 1


def test_race_not_in_betfair_counted_unmatched():
    horses, stats = find_horses_by_name(_betfair(off="2026-07-22T15:00:00+01:00"), _eight88())
    assert horses == []
    assert stats.races_unmatched == 1
    assert stats.races_matched == 0


def test_runner_name_mismatch_counted():
    horses, stats = find_horses_by_name(_betfair(), _eight88(runner_name="Ghost Horse"))
    assert horses == []
    assert stats.races_matched == 1
    assert stats.runners_unmatched == 1
    assert stats.runners_priced == 0


def test_venue_drift_still_matches():
    horses, _ = find_horses_by_name(_betfair(venue="Worcester (AW)"), _eight88(venue="Worcester"))
    assert len(horses) == 1


def test_null_each_way_skipped():
    e = _eight88()
    e.races[0] = replace(e.races[0], each_way_terms=None)
    horses, stats = find_horses_by_name(_betfair(), e)
    assert horses == []
    assert stats.races_matched == 1  # race matched, but unpriceable
    assert stats.races_unpriceable == 1


def test_places_out_of_range_skipped():
    # Betfair's to-be-placed markets stop at TOP_5, so a 6-place race matches
    # Betfair but cannot be priced — it must be reported as unpriceable, not
    # silently folded into "matched".
    horses, stats = find_horses_by_name(_betfair(), _eight88(places=6))
    assert horses == []
    assert stats.races_matched == 1
    assert stats.races_unpriceable == 1


def test_place_market_absent_skipped():
    bf = _betfair()
    bf.races[0] = replace(
        bf.races[0],
        market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z"},
        runners=[RunnerOdds("Holy Legend", {MarketType.WIN: 2.0}, 99)])
    horses, _ = find_horses_by_name(bf, _eight88())
    assert horses == []


def test_zero_lay_skipped():
    assert find_horses_by_name(_betfair(0.0, 1.4), _eight88())[0] == []
    assert find_horses_by_name(_betfair(2.0, 0.0), _eight88())[0] == []


def test_null_win_price_skipped():
    e = _eight88()
    e.races[0] = replace(
        e.races[0],
        runners=[replace(e.races[0].runners[0], win_price=None, win_price_raw=None)])
    assert find_horses_by_name(_betfair(), e)[0] == []


def test_sorted_by_edge_desc():
    bf = ScrapeOutput(
        "2026-07-22T12:00:00Z", 1,
        [RaceOdds("1.1", "Worcester", "GB", "2026-07-22T13:55:00+01:00", "u",
                  "12:55 Worcester",
                  {MarketType.WIN: "2026-07-22T12:00:00Z",
                   MarketType.TOP_3: "2026-07-22T12:00:00Z"},
                  [RunnerOdds("A", {MarketType.WIN: 2.0, MarketType.TOP_3: 1.4}, 1),
                   RunnerOdds("B", {MarketType.WIN: 2.0, MarketType.TOP_3: 1.2}, 2)])])
    e = Sport888Output(
        "2026-07-22T12:00:30Z", 1,
        [Sport888Race("Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00",
                      "Winner Market", "2026-07-22T12:00:30Z", EachWayTerms(0.2, 3),
                      [Sport888Runner("A", 3.0, "2/1"), Sport888Runner("B", 3.0, "2/1")])])
    horses, _ = find_horses_by_name(bf, e)
    assert [h.edge for h in horses] == sorted([h.edge for h in horses], reverse=True)
    assert horses[0].runner.selection_id == 2  # B has higher edge (1.2 place lay)
