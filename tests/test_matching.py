from betfair_scraper.models import RaceOdds, RunnerOdds
from common.markettype import MarketType
from arb_finder.matching import (
    match_race,
    match_runner,
    normalize_name,
    normalize_venue,
    to_instant,
)


def _race(venue, off_time, runners) -> RaceOdds:
    return RaceOdds(
        race_id="1.1", venue=venue, country="GB", off_time=off_time,
        win_market_url="u", market_name="m",
        market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z"},
        runners=runners)


class TestNormalize:
    def test_name_strips_case_punct_space(self):
        assert normalize_name("O'Brien's Pride") == normalize_name("obriens pride")

    def test_name_folds_accents(self):
        assert normalize_name("Fánchén") == normalize_name("Fanchen")

    def test_venue_strips_suffix_punct(self):
        assert normalize_venue("Newmarket (July)") == "newmarketjuly"
        assert normalize_venue("Worcester") == "worcester"


class TestToInstant:
    def test_same_instant_across_offsets(self):
        assert to_instant("2026-07-22T12:55:00+00:00") == to_instant("2026-07-22T13:55:00+01:00")

    def test_z_suffix(self):
        assert to_instant("2026-07-22T12:55:00Z") == to_instant("2026-07-22T12:55:00+00:00")

    def test_bad_input(self):
        assert to_instant("nope") is None


class TestMatchRace:
    def test_venue_and_instant_match(self):
        bf = [_race("Worcester", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Worcester", bf)
        assert got is bf[0]

    def test_venue_drift_falls_back_to_unique_instant(self):
        bf = [_race("Worcester (AW)", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Worcester", bf)
        assert got is bf[0]

    def test_no_match_when_instant_absent(self):
        bf = [_race("Worcester", "2026-07-22T14:00:00+01:00", [])]
        assert match_race("2026-07-22T12:55:00+00:00", "Worcester", bf) is None

    def test_two_venues_same_instant_no_venue_match_is_ambiguous(self):
        bf = [_race("Ascot", "2026-07-22T13:55:00+01:00", []),
              _race("Naas", "2026-07-22T13:55:00+01:00", [])]
        assert match_race("2026-07-22T12:55:00+00:00", "Worcester", bf) is None

    def test_two_venues_same_instant_venue_disambiguates(self):
        bf = [_race("Ascot", "2026-07-22T13:55:00+01:00", []),
              _race("Naas", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Naas", bf)
        assert got.venue == "Naas"


class TestMatchRunner:
    def test_exact_normalized_match(self):
        race = _race("Worcester", "2026-07-22T13:55:00+01:00",
                     [RunnerOdds("Holy Legend", {MarketType.WIN: 4.0}, 1)])
        got = match_runner("Holy Legend", race)
        assert got.selection_id == 1

    def test_no_match_returns_none(self):
        race = _race("Worcester", "2026-07-22T13:55:00+01:00",
                     [RunnerOdds("Holy Legend", {MarketType.WIN: 4.0}, 1)])
        assert match_runner("Different Horse", race) is None

    def test_ambiguous_same_normalized_name_returns_none(self):
        # "Holy Legend" and "holy-legend!" both normalize to "holylegend"
        race = _race("Worcester", "2026-07-22T13:55:00+01:00",
                     [RunnerOdds("Holy Legend", {MarketType.WIN: 4.0}, 1),
                      RunnerOdds("holy-legend!", {MarketType.WIN: 5.0}, 2)])
        assert match_runner("Holy Legend", race) is None
