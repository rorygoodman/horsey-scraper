"""Tests for races.py: parsing the racing-page/v7 per-meeting response."""

import pytest

from paddypower_scraper.models import PaddyRace, PaddyRunner
from paddypower_scraper.races import (
    SYNTHETIC_RUNNER_NAMES,
    _market_name,
    _parse_eachway,
    _parse_runners,
    _utc_to_london,
    parse_meeting_response,
)

from conftest import mutate

SCRAPED_AT = "2026-05-26T18:00:00Z"


class TestParseMeetingResponse:
    def test_returns_races(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        assert len(races) > 0
        assert all(isinstance(r, PaddyRace) for r in races)

    def test_skips_exchange_history_rows(self, racing_page_payload):
        # Some entries in payload['races'] have winMarketId=null (exchange results).
        # The fixture has these (raceIds starting with '1.201.').
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # Exactly one race in the fixture has a present WIN market; the rest are
        # exchange-history rows (null winMarketId) or have absent markets.
        assert len(races) == 1
        # Real bookmaker races have raceIds like '35646567.1800'
        for r in races:
            # Real races have venue / country / off_time populated
            assert r.venue
            assert r.country
            assert r.off_time

    def test_propagates_scraped_at(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        assert all(r.scraped_at == SCRAPED_AT for r in races)

    def test_each_way_terms_present(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # At least one race in the fixture has eachwayAvailable
        ew_races = [r for r in races if r.each_way_terms is not None]
        assert ew_races
        ew = ew_races[0].each_way_terms
        assert 0.0 < ew.fraction <= 1.0
        assert 1 <= ew.places <= 6

    def test_betfair_win_market_id_threaded(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # At least some races should have an exchange id
        with_id = [r for r in races if r.betfair_win_market_id]
        assert with_id

    def test_runners_populated_with_active_odds(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        any_runner_with_price = any(
            rr.win_price is not None for r in races for rr in r.runners
        )
        assert any_runner_with_price

    def test_drops_synthetic_runners(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        for r in races:
            for rr in r.runners:
                assert rr.name not in SYNTHETIC_RUNNER_NAMES

    def test_removed_runner_kept_with_null_prices(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # The Ballinrobe fixture's first race has a REMOVED 'Grainne A Chroi'
        all_runners = [rr for r in races for rr in r.runners]
        non_runners = [rr for rr in all_runners
                       if rr.win_price is None and rr.win_price_raw is None]
        assert non_runners, "fixture should have at least one non-runner"

    def test_skips_race_with_missing_win_market(self, racing_page_payload):
        baseline = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        p = mutate(racing_page_payload)
        # Pick the first race whose winMarketId is actually present in markets
        # (i.e. one that currently contributes a race); delete that market.
        victim_wmid = next(
            r["winMarketId"] for r in p["races"].values()
            if r.get("winMarketId") and r["winMarketId"] in p["markets"]
        )
        del p["markets"][victim_wmid]
        races = parse_meeting_response(p, SCRAPED_AT)
        assert len(races) == len(baseline) - 1

    def test_drops_race_with_no_usable_runners(self, racing_page_payload):
        baseline = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        p = mutate(racing_page_payload)
        victim_wmid = next(
            r["winMarketId"] for r in p["races"].values()
            if r.get("winMarketId") and r["winMarketId"] in p["markets"]
        )
        p["markets"][victim_wmid]["runners"] = []
        races = parse_meeting_response(p, SCRAPED_AT)
        assert len(races) == len(baseline) - 1

    def test_market_with_eachway_unavailable(self, racing_page_payload):
        p = mutate(racing_page_payload)
        for m in p["markets"].values():
            m["eachwayAvailable"] = False
        races = parse_meeting_response(p, SCRAPED_AT)
        assert all(r.each_way_terms is None for r in races)


class TestParseRunners:
    def _market(self, runners):
        return {"runners": runners}

    def test_synthetic_dropped(self):
        m = self._market([
            {"runnerName": "Unnamed Favourite", "selectionId": 1,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 2.0},
                 "fractionalOdds": {"numerator": 1, "denominator": 1}}}},
            {"runnerName": "Real Horse", "selectionId": 2,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 3.0},
                 "fractionalOdds": {"numerator": 2, "denominator": 1}}}},
        ])
        runners = _parse_runners(m)
        assert [r.name for r in runners] == ["Real Horse"]

    def test_removed_keeps_runner_null_prices(self):
        m = self._market([
            {"runnerName": "Withdrawn", "selectionId": 7,
             "runnerStatus": "REMOVED",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 5.0},
                 "fractionalOdds": {"numerator": 4, "denominator": 1}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Withdrawn", selection_id=7,
                                       win_price=None, win_price_raw=None)]

    def test_active_with_valid_odds(self):
        m = self._market([
            {"runnerName": "Live Horse", "selectionId": 9,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 7.5},
                 "fractionalOdds": {"numerator": 13, "denominator": 2}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Live Horse", selection_id=9,
                                       win_price=7.5, win_price_raw="13/2")]

    def test_parity_invariant_malformed_fractional_nulls_both(self):
        m = self._market([
            {"runnerName": "Half Odds", "selectionId": 3,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 4.0},
                 # numerator/denominator missing — malformed fractional
                 "fractionalOdds": {}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Half Odds", selection_id=3,
                                       win_price=None, win_price_raw=None)]

    def test_active_without_odds_nulls_both(self):
        m = self._market([
            {"runnerName": "No Odds", "selectionId": 4,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="No Odds", selection_id=4,
                                       win_price=None, win_price_raw=None)]

    def test_missing_runner_name_skipped(self):
        m = self._market([
            {"selectionId": 11, "runnerStatus": "ACTIVE"},
            {"runnerName": "Named", "selectionId": 12, "runnerStatus": "ACTIVE",
             "winRunnerOdds": {}},
        ])
        runners = _parse_runners(m)
        assert [r.name for r in runners] == ["Named"]


class TestParseEachway:
    def test_unavailable(self):
        assert _parse_eachway({"eachwayAvailable": False}) is None

    def test_missing_places(self):
        assert _parse_eachway({"eachwayAvailable": True}) is None

    def test_zero_places(self):
        assert _parse_eachway({"eachwayAvailable": True, "numberOfPlaces": 0,
                               "placeFraction": {"numerator": 1, "denominator": 5}}) is None

    def test_missing_fraction(self):
        assert _parse_eachway({"eachwayAvailable": True, "numberOfPlaces": 3}) is None

    def test_invalid_fraction(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 2, "denominator": 1}}  # 2/1 > 1
        assert _parse_eachway(m) is None

    def test_zero_denominator(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 0}}
        assert _parse_eachway(m) is None

    def test_valid_fifth(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 5}}
        ew = _parse_eachway(m)
        assert ew is not None
        assert ew.fraction == pytest.approx(0.2)
        assert ew.places == 3

    def test_default_true_when_field_missing(self):
        # Spec: when eachwayAvailable is absent, treat as True (see races.py _parse_eachway)
        m = {"numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 4}}
        ew = _parse_eachway(m)
        assert ew is not None
        assert ew.places == 3


class TestUtcToLondon:
    def test_bst(self):
        assert _utc_to_london("2026-06-15T17:00:00.000Z") == "2026-06-15T18:00:00+01:00"

    def test_gmt(self):
        assert _utc_to_london("2026-12-15T17:00:00.000Z") == "2026-12-15T17:00:00Z"

    def test_invalid_returns_none(self):
        assert _utc_to_london("not-a-date") is None

    def test_empty_returns_none(self):
        assert _utc_to_london("") is None

    def test_naive_treated_as_utc(self):
        # No tz marker → treated as UTC, then converted to London (June=BST)
        assert _utc_to_london("2026-06-15T17:00:00") == "2026-06-15T18:00:00+01:00"


class TestMarketName:
    def test_with_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "2m1f Hcap Chs") == \
            "18:00 Plumpton - 2m1f Hcap Chs"

    def test_without_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "") == \
            "18:00 Plumpton"

    def test_blank_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "   ") == \
            "18:00 Plumpton"
