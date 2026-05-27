"""Tests for arb_finder.calculator (find_horses + each-way edge)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from common.markettype import MarketType
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)
from arb_finder.calculator import each_way_arb_margin, find_horses


class TestEdgeFormula:
    def test_known_value(self):
        # p=3, f=0.2, bw=2.0, bp=1.4 → 0.75 + 0.5 - 1 = 0.25
        assert each_way_arb_margin(3.0, 0.2, 2.0, 1.4) == pytest.approx(0.25)

    def test_negative(self):
        assert each_way_arb_margin(2.0, 0.2, 4.0, 3.0) < 0

    def test_equilibrium_is_zero(self):
        # bw == p and bp == 1 + (p-1)*f  ->  lw = 0.5, lp = 0.5  ->  edge = 0
        p, f = 4.0, 0.2
        assert each_way_arb_margin(p, f, p, 1 + (p - 1) * f) == pytest.approx(0.0)

    def test_champ_worked_example(self):
        # p=11, f=0.2, bw=10, bp=2.5 -> 0.55 + 0.6 - 1 = 0.15
        assert each_way_arb_margin(11.0, 0.2, 10.0, 2.5) == pytest.approx(0.15)


def _betfair(win_lay, place_lay) -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-05-25T17:05:56.890289Z",
        race_count=1,
        races=[RaceOdds(
            race_id="1.1", venue="Ascot", country="GB",
            off_time="2026-05-25T18:00:00+01:00", win_market_url="u",
            market_name="18:00 Ascot",
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z",
                               MarketType.TOP_2: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds(
                name="A", lay={MarketType.WIN: win_lay, MarketType.TOP_2: place_lay},
                selection_id=1)],
        )],
    )


def _paddy() -> PaddyOutput:
    return PaddyOutput(
        scraped_at="2026-05-25T17:05:58.384555Z",
        race_count=1,
        races=[PaddyRace(
            venue="Ascot", country="GB", off_time="2026-05-25T18:00:00+01:00",
            market_name="18:00 Ascot", race_url="r",
            scraped_at="2026-05-25T17:05:58.384555Z",
            betfair_win_market_id="1.1",
            each_way_terms=EachWayTerms(fraction=0.2, places=2),
            runners=[PaddyRunner("A", 1, 3.0, "2/1")],
        )],
    )


class TestFindHorses:
    def test_positive_edge_included(self):
        horses = find_horses(_betfair(2.0, 1.4), _paddy())
        assert len(horses) == 1
        assert horses[0].runner.selection_id == 1
        assert horses[0].betfair.place_market is MarketType.TOP_2
        assert horses[0].betfair.place_lay == 1.4
        assert horses[0].edge == pytest.approx(0.25)

    def test_negative_edge_still_included(self):
        # The headline change vs arbs.json: negative edges are KEPT.
        horses = find_horses(_betfair(4.0, 3.0), _paddy())
        assert len(horses) == 1
        assert horses[0].edge < 0

    def test_skip_when_place_market_absent(self):
        bf = _betfair(2.0, 1.4)
        race = bf.races[0]
        bf.races[0] = RaceOdds(
            race_id=race.race_id, venue=race.venue, country=race.country,
            off_time=race.off_time, win_market_url=race.win_market_url,
            market_name=race.market_name,
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds("A", {MarketType.WIN: 2.0}, 1)])
        assert find_horses(bf, _paddy()) == []

    def test_skip_zero_lay(self):
        assert find_horses(_betfair(0.0, 1.4), _paddy()) == []
        assert find_horses(_betfair(2.0, 0.0), _paddy()) == []

    def test_skip_paddy_race_not_in_betfair(self):
        paddy = _paddy()
        paddy.races[0] = replace(paddy.races[0], betfair_win_market_id="9.999")
        assert find_horses(_betfair(2.0, 1.4), paddy) == []

    def test_skip_runner_selection_id_mismatch(self):
        paddy = _paddy()
        paddy.races[0] = replace(
            paddy.races[0],
            runners=[replace(paddy.races[0].runners[0], selection_id=999)])
        assert find_horses(_betfair(2.0, 1.4), paddy) == []

    def test_skip_null_each_way_terms(self):
        paddy = _paddy()
        paddy.races[0] = replace(paddy.races[0], each_way_terms=None)
        assert find_horses(_betfair(2.0, 1.4), paddy) == []

    def test_skip_null_win_price(self):
        paddy = _paddy()
        paddy.races[0] = replace(
            paddy.races[0],
            runners=[replace(paddy.races[0].runners[0],
                             win_price=None, win_price_raw=None)])
        assert find_horses(_betfair(2.0, 1.4), paddy) == []

    def test_skip_null_win_lay(self):
        bf = _betfair(2.0, 1.4)
        bf.races[0] = replace(
            bf.races[0],
            runners=[replace(bf.races[0].runners[0],
                             lay={MarketType.WIN: None, MarketType.TOP_2: 1.4})])
        assert find_horses(bf, _paddy()) == []

    def test_skip_places_out_of_range(self):
        paddy = _paddy()
        paddy.races[0] = replace(
            paddy.races[0], each_way_terms=EachWayTerms(fraction=0.2, places=6))
        assert find_horses(_betfair(2.0, 1.4), paddy) == []

    def test_sorted_by_edge_desc(self):
        bf = ScrapeOutput(
            "2026-05-25T17:05:56Z", 1,
            [RaceOdds("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u",
                      "18:00 Ascot",
                      {MarketType.WIN: "2026-05-25T17:05:58Z",
                       MarketType.TOP_2: "2026-05-25T17:05:58Z"},
                      [RunnerOdds("A", {MarketType.WIN: 2.0, MarketType.TOP_2: 1.4}, 1),
                       RunnerOdds("B", {MarketType.WIN: 2.0, MarketType.TOP_2: 1.2}, 2)])])
        paddy = PaddyOutput(
            "2026-05-25T17:05:58Z", 1,
            [PaddyRace("Ascot", "GB", "2026-05-25T18:00:00+01:00", "18:00 Ascot",
                       "r", "2026-05-25T17:05:58Z", "1.1",
                       EachWayTerms(0.2, 2),
                       [PaddyRunner("A", 1, 3.0, "2/1"),
                        PaddyRunner("B", 2, 3.0, "2/1")])])
        horses = find_horses(bf, paddy)
        assert [h.edge for h in horses] == sorted([h.edge for h in horses], reverse=True)
        assert horses[0].runner.selection_id == 2  # B (1.2 place lay) has the higher edge
