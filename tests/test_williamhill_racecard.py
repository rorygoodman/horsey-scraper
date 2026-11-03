"""Each-way terms come from the Win market's structured fields, confirmed by
its caption. Unlike Novibet's sysname, these already carry Extra Places
terms (checked across all 76 GB/IE + US each-way races on the capture day),
but a disagreement drops the terms rather than guessing: wrong terms always
bias toward phantom arbs."""

from __future__ import annotations

import pytest

from williamhill_scraper.models import EachWayTerms, WilliamHillRunner
from williamhill_scraper.racecard import (
    each_way_terms, parse_each_way_caption, parse_racecard,
)
from conftest import mutate  # repo convention: tests/ is not a package

SCRAPED = "2026-11-03T12:00:00Z"


def _parse(payload, venue="Warwick", country="uk-ireland"):
    return parse_racecard(payload, SCRAPED, venue=venue, country=country)


def _win_market(payload):
    col = next(c for c in payload["raceCardData"]["marketCollections"]
               if c["name"] == "Racecard")
    return col["markets"][0]


class TestParseEachWayCaption:
    def test_standard(self):
        assert parse_each_way_caption("EW: 1/5 Odds 3 Places") == (1, 5, 3)

    def test_quarter_odds(self):
        assert parse_each_way_caption("EW: 1/4 Odds 2 Places") == (1, 4, 2)

    def test_unparseable(self):
        for bad in (None, "", "Win Only", "1/5 Odds", "EW: 1/5 Odds"):
            assert parse_each_way_caption(bad) is None, bad


class TestEachWayTerms:
    def test_structured_and_caption_agree(self):
        m = {"eachWay": "EW: 1/5 Odds 3 Places", "eachWayFactorNum": 1,
             "eachWayFactorDen": 5, "eachWayPlaces": 3}
        assert each_way_terms(m) == EachWayTerms(0.2, 3)

    def test_win_only_has_no_terms(self):
        m = {"eachWay": "Win Only", "eachWayFactorNum": 1,
             "eachWayFactorDen": 1, "eachWayPlaces": 1}
        assert each_way_terms(m) is None

    def test_disagreement_drops_terms(self, capsys):
        m = {"eachWay": "EW: 1/5 Odds 4 Places", "eachWayFactorNum": 1,
             "eachWayFactorDen": 5, "eachWayPlaces": 3}
        assert each_way_terms(m) is None
        assert "disagrees" in capsys.readouterr().err

    def test_missing_structured_fields(self):
        assert each_way_terms({"eachWay": "EW: 1/5 Odds 3 Places"}) is None


def test_standard_race(williamhill_racecard_3pl):
    race = _parse(williamhill_racecard_3pl)
    assert race.venue == "Warwick"
    assert race.country == "uk-ireland"
    assert race.off_time == "2026-11-03T15:48:00Z"
    assert race.market_name == "Win"
    assert race.scraped_at == SCRAPED
    assert race.each_way_terms == EachWayTerms(0.2, 3)
    assert len(race.runners) == 10
    assert race.runners[0] == WilliamHillRunner("An Buachaill Rua", 11.0, "10/1")
    assert WilliamHillRunner("Ballymoreen", 3.5, "5/2") in race.runners


def test_extra_places_race_uses_boosted_terms(williamhill_racecard_extra_places):
    # 15 runners would normally be 3 places; the promo takes it to 4. The
    # Each Way Extra 5-7 place markets in the same payload must be ignored.
    race = _parse(williamhill_racecard_extra_places, venue="Fairyhouse")
    assert race.each_way_terms == EachWayTerms(0.2, 4)


def test_non_runners_are_dropped(williamhill_racecard_extra_places):
    race = _parse(williamhill_racecard_extra_places, venue="Fairyhouse")
    names = {r.name for r in race.runners}
    assert len(race.runners) == 15
    for nr in ("Colesberg", "George's Angel", "Undertheinfluence", "Santa Paula"):
        assert nr not in names
    assert all(r.win_price is not None for r in race.runners)


def test_non_runner_flagged_only_on_runner_is_dropped(williamhill_racecard_3pl):
    p = mutate(williamhill_racecard_3pl)
    p["event"]["runners"]["OB_RN21647331"]["active"] = False  # An Buachaill Rua
    names = {r.name for r in _parse(p).runners}
    assert "An Buachaill Rua" not in names


def test_suspended_runner_is_kept_unpriced(williamhill_racecard_3pl):
    p = mutate(williamhill_racecard_3pl)
    p["raceCardData"]["selections"]["OB_OU6574327606"]["status"] = "S"
    race = _parse(p)
    assert race.runners[0] == WilliamHillRunner("An Buachaill Rua", None, None)


def test_selection_from_another_market_is_not_used(williamhill_racecard_3pl):
    p = mutate(williamhill_racecard_3pl)
    p["raceCardData"]["selections"]["OB_OU6574327606"]["marketId"] = "OB_MA_OTHER"
    assert _parse(p).runners[0].win_price is None


def test_win_only_race_has_runners_but_no_terms(williamhill_racecard_win_only):
    race = _parse(williamhill_racecard_win_only)
    assert race.each_way_terms is None
    assert WilliamHillRunner("Court In A Storm", 2.25, "5/4") in race.runners


def test_caption_mismatch_drops_terms_but_keeps_race(williamhill_racecard_3pl):
    p = mutate(williamhill_racecard_3pl)
    _win_market(p)["eachWay"] = "EW: 1/5 Odds 4 Places"
    race = _parse(p)
    assert race is not None and race.each_way_terms is None


def test_race_at_the_off_is_none(williamhill_racecard_at_off):
    assert _parse(williamhill_racecard_at_off) is None


@pytest.mark.parametrize("breaker", [
    lambda p: p.pop("event"),
    lambda p: p["event"].__setitem__("startDateTime", "soon"),
    lambda p: p["raceCardData"].__setitem__("marketCollections", []),
    lambda p: _win_market(p).__setitem__("name", "Win - In Play"),
])
def test_malformed_payloads_are_none(williamhill_racecard_3pl, breaker):
    p = mutate(williamhill_racecard_3pl)
    breaker(p)
    assert _parse(p) is None


def test_bst_off_time_is_london_offset(williamhill_racecard_3pl):
    p = mutate(williamhill_racecard_3pl)
    p["event"]["startDateTime"] = "2026-07-31T13:00:00.000+0000"
    assert _parse(p).off_time == "2026-07-31T14:00:00+01:00"
