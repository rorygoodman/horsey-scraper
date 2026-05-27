"""Tests for arb_finder.calculator."""

from __future__ import annotations

import pytest

from common.markettype import MarketType
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)
from arb_finder.calculator import each_way_arb_margin, find_arbs


class TestMargin:
    def test_known_value(self):
        # p=3, f=0.2, bw=2.0, bp=1.4:
        # lw = 3/4 = 0.75; lp = (1 + 2*0.2)/2.8 = 1.4/2.8 = 0.5; margin = 0.25
        assert each_way_arb_margin(3.0, 0.2, 2.0, 1.4) == pytest.approx(0.25)

    def test_no_arb_negative(self):
        assert each_way_arb_margin(2.0, 0.2, 4.0, 3.0) < 0

    def test_champ_example(self):
        # p=11.0, f=0.2, bw=10.0, bp=2.5 → margin 0.15
        # L_w = 11/(2*10) = 0.55; L_p = (1 + 10*0.2) / (2*2.5) = 3/5 = 0.60
        assert each_way_arb_margin(11.0, 0.2, 10.0, 2.5) == pytest.approx(0.15)

    def test_equilibrium_gives_zero(self):
        # bw == p and bp == 1 + (p-1)*f → margin == 0
        p = 7.0
        f = 0.25
        bp = 1.0 + (p - 1.0) * f  # 2.5
        assert each_way_arb_margin(p, f, p, bp) == pytest.approx(0.0, abs=1e-12)

    def test_wider_bf_prices_negative(self):
        assert each_way_arb_margin(11.0, 0.2, 15.0, 4.0) < 0.0

    def test_bp_of_1_is_finite_and_positive(self):
        # bp = 1.0 → L_p blows up positively, still finite
        m = each_way_arb_margin(11.0, 0.2, 10.0, 1.0)
        assert isinstance(m, float) and m > 0.0

    def test_f_of_zero_is_finite(self):
        m = each_way_arb_margin(5.0, 0.0, 5.0, 2.0)
        assert isinstance(m, float)

    def test_quarter_odds_5_places(self):
        # p=6.0, f=0.25, bw=5.5, bp=2.0
        expected = 6.0 / (2.0 * 5.5) + (1.0 + (6.0 - 1.0) * 0.25) / (2.0 * 2.0) - 1.0
        assert each_way_arb_margin(6.0, 0.25, 5.5, 2.0) == pytest.approx(expected)


def _betfair(win_lay, top_lay) -> ScrapeOutput:
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
                name="A", lay={MarketType.WIN: win_lay, MarketType.TOP_2: top_lay},
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


class TestFindArbs:
    def test_positive_margin_emitted(self):
        arbs = find_arbs(_betfair(2.0, 1.4), _paddy())
        assert len(arbs) == 1
        assert arbs[0].runner.selection_id == 1
        assert arbs[0].betfair.top_n_type is MarketType.TOP_2
        assert arbs[0].margin == pytest.approx(0.25)

    def test_non_positive_margin_skipped(self):
        assert find_arbs(_betfair(4.0, 3.0), _paddy()) == []

    def test_zero_lay_skipped_not_crashed(self):
        # A 0.0 lay (only possible from corrupt input) must be skipped, not
        # raise ZeroDivisionError in the margin formula.
        assert find_arbs(_betfair(0.0, 1.4), _paddy()) == []
        assert find_arbs(_betfair(2.0, 0.0), _paddy()) == []

    def test_skip_when_topn_market_absent(self):
        bf = _betfair(2.0, 1.4)
        race = bf.races[0]
        bf.races[0] = RaceOdds(
            race_id=race.race_id, venue=race.venue, country=race.country,
            off_time=race.off_time, win_market_url=race.win_market_url,
            market_name=race.market_name,
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds("A", {MarketType.WIN: 2.0}, 1)])
        assert find_arbs(bf, _paddy()) == []

    def test_sorted_by_margin_desc(self):
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
        arbs = find_arbs(bf, paddy)
        assert [a.runner.selection_id for a in arbs] == [2, 1]  # B (1.2 lay) > A

    # --- Oracle-derived extra tests from FindArbsTest.kt ---

    def test_race_in_paddy_not_betfair_skipped(self):
        betfair = ScrapeOutput("2026-05-13T22:00:00Z", 0, [])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("X", 1, 11.0, "10/1")])])
        assert find_arbs(betfair, paddy) == []

    def test_runner_no_matching_selection_id_skipped(self):
        # BF has runner 999, Paddy wants 1001 — no match
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Other", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 999)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Champ", 1001, 11.0, "10/1")])])
        assert find_arbs(betfair, paddy) == []

    def test_paddy_race_with_null_each_way_terms_skipped(self):
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 1001)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       each_way_terms=None,
                       runners=[PaddyRunner("Champ", 1001, 11.0, "10/1")])])
        assert find_arbs(betfair, paddy) == []

    def test_non_runner_null_win_price_skipped(self):
        # PaddyRunner with winPrice=None and winPriceRaw=None is a non-runner
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 1001)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Champ", 1001, None, None)])])
        assert find_arbs(betfair, paddy) == []

    def test_null_win_lay_skipped(self):
        # BF runner has no WIN lay price
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: None, MarketType.TOP_4: 2.5}, 1001)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Champ", 1001, 11.0, "10/1")])])
        assert find_arbs(betfair, paddy) == []

    def test_ew_places_outside_2_to_5_skipped(self):
        # places=6 → top_n_from_places returns None → skip
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 1001)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 6),
                       [PaddyRunner("Champ", 1001, 11.0, "10/1")])])
        assert find_arbs(betfair, paddy) == []

    def test_champ_example_find_arbs(self):
        # Full worked example: p=11, f=0.2, bw=10, bp=2.5 → margin=0.15, TOP_4
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 1,
            [RaceOdds("1.x", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 1001)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 1,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.x",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Champ", 1001, 11.0, "10/1")])])
        arbs = find_arbs(betfair, paddy)
        assert len(arbs) == 1
        assert arbs[0].runner.name == "Champ"
        assert arbs[0].runner.selection_id == 1001
        assert arbs[0].margin == pytest.approx(0.15, abs=1e-9)
        assert arbs[0].betfair.top_n_type is MarketType.TOP_4

    def test_multiple_races_sorted_desc(self):
        # Race A: margin 0.15; Race B: bp=2.0 → bigger margin
        betfair = ScrapeOutput(
            "2026-05-13T22:00:00Z", 2,
            [RaceOdds("1.A", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Champ", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.5}, 1001)]),
             RaceOdds("1.B", "Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                      "u", "17:40 Lingfield",
                      {MarketType.WIN: "2026-05-13T22:00:00Z",
                       MarketType.TOP_4: "2026-05-13T22:00:00Z"},
                      [RunnerOdds("Hero", {MarketType.WIN: 10.0, MarketType.TOP_4: 2.0}, 2002)])])
        paddy = PaddyOutput(
            "2026-05-13T22:00:01Z", 2,
            [PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.A",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Champ", 1001, 11.0, "10/1")]),
             PaddyRace("Lingfield", "GB", "2026-05-14T17:40:00+01:00",
                       "17:40 Lingfield", "", "2026-05-13T22:00:01Z", "1.B",
                       EachWayTerms(0.2, 4),
                       [PaddyRunner("Hero", 2002, 11.0, "10/1")])])
        arbs = find_arbs(betfair, paddy)
        assert len(arbs) == 2
        assert arbs[0].margin > arbs[1].margin
        assert arbs[0].runner.name == "Hero"
