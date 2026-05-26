"""Tests for betfair_scraper.responses."""

from __future__ import annotations

import json

import pytest

from common.markettype import MarketType  # noqa: F401 (parity import)
from betfair_scraper.responses import (
    MarketBookStatus,
    build_book_body,
    build_catalogue_body,
    build_login_body,
    lay_prices_from_book,
    parse_ssoid,
    race_from_catalogue,
)


class TestParseSsoid:
    def test_success(self):
        assert parse_ssoid('{"status":"SUCCESS","token":"abc123"}') == "abc123"

    def test_restricted_mentions_2fa(self):
        with pytest.raises(RuntimeError, match="2FA"):
            parse_ssoid('{"status":"LOGIN_RESTRICTED"}')

    def test_other_failure(self):
        with pytest.raises(RuntimeError, match="status=FAIL"):
            parse_ssoid('{"status":"FAIL"}')

    def test_success_without_token(self):
        with pytest.raises(RuntimeError, match="no token"):
            parse_ssoid('{"status":"SUCCESS"}')

    def test_malformed(self):
        with pytest.raises(RuntimeError, match="not a valid JSON object"):
            parse_ssoid("{not json")

    def test_restricted_includes_status_string(self):
        # Kotlin oracle: error message contains "LOGIN_RESTRICTED" as well as "2FA"
        with pytest.raises(RuntimeError, match="LOGIN_RESTRICTED"):
            parse_ssoid('{"status":"LOGIN_RESTRICTED"}')

    def test_null_token_on_success(self):
        # JSON null is distinct from absent key; both must raise "no token"
        with pytest.raises(RuntimeError, match="no token"):
            parse_ssoid('{"status":"SUCCESS","token":null}')


class TestRaceFromCatalogue:
    def test_full(self):
        obj = {
            "marketId": "1.258528220",
            "marketStartTime": "2026-05-25T17:05:00Z",
            "event": {"venue": "Ballinrobe", "countryCode": "IE"},
        }
        race = race_from_catalogue(obj)
        assert race.race_id == "1.258528220"
        assert race.venue == "Ballinrobe"
        assert race.country == "IE"
        assert race.off_time == "2026-05-25T18:05:00+01:00"
        assert race.win_market_url.endswith("/market/1.258528220")

    def test_missing_venue_returns_none(self):
        obj = {"marketId": "1.1", "marketStartTime": "2026-05-25T17:05:00Z",
               "event": {"countryCode": "IE"}}
        assert race_from_catalogue(obj) is None

    def test_bad_start_time_returns_none(self):
        obj = {"marketId": "1.1", "marketStartTime": "nope",
               "event": {"venue": "X", "countryCode": "IE"}}
        assert race_from_catalogue(obj) is None

    def test_winter_utc_offset(self):
        # Kotlin oracle: January date → GMT, off_time ends with 'Z' (no +01:00)
        obj = {
            "marketId": "1.1",
            "marketStartTime": "2026-01-15T14:30:00.000Z",
            "event": {"venue": "Lingfield", "countryCode": "GB"},
        }
        race = race_from_catalogue(obj)
        assert race is not None
        assert race.off_time == "2026-01-15T14:30:00Z"


class TestLayPricesFromBook:
    def test_open_with_lays(self):
        obj = {
            "status": "OPEN",
            "runners": [
                {"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}, {"price": 3.0}]}},
                {"selectionId": 2, "ex": {"availableToLay": []}},
            ],
        }
        snap = lay_prices_from_book(obj)
        assert snap.status is MarketBookStatus.OPEN
        assert snap.lay_by_selection_id == {1: 2.5, 2: None}

    def test_non_open_is_empty(self):
        snap = lay_prices_from_book({"status": "SUSPENDED", "runners": []})
        assert snap.status is MarketBookStatus.OTHER
        assert snap.lay_by_selection_id == {}

    def test_unknown_status_is_other(self):
        # Kotlin oracle: "WEIRD" (unknown) status → MarketBookStatus.OTHER
        snap = lay_prices_from_book({"status": "WEIRD", "runners": []})
        assert snap.status is MarketBookStatus.OTHER
        assert snap.lay_by_selection_id == {}

    def test_non_numeric_price_is_none(self):
        # A malformed/non-numeric first-offer price must not propagate a
        # non-float into lay_by_selection_id (annotated dict[int, float|None]).
        obj = {
            "status": "OPEN",
            "runners": [
                {"selectionId": 1, "ex": {"availableToLay": [{"price": "bad"}]}},
                {"selectionId": 2, "ex": {"availableToLay": [{"price": True}]}},
            ],
        }
        snap = lay_prices_from_book(obj)
        assert snap.lay_by_selection_id == {1: None, 2: None}

    def test_open_multiple_runners_with_and_without_lays(self):
        # Mirrors Kotlin oracle fixture: selectionIds 111/222/333, multi-price lays
        obj = {
            "status": "OPEN",
            "runners": [
                {"selectionId": 111, "ex": {"availableToLay": [
                    {"price": 4.8, "size": 12.5}, {"price": 5.0, "size": 25.0}]}},
                {"selectionId": 222, "ex": {"availableToLay": []}},
                {"selectionId": 333, "ex": {"availableToLay": [
                    {"price": 22.0, "size": 4.0}]}},
            ],
        }
        snap = lay_prices_from_book(obj)
        assert snap.status is MarketBookStatus.OPEN
        assert snap.lay_by_selection_id == {111: 4.8, 222: None, 333: 22.0}


class TestBuildBodies:
    def test_login_body_urlencoded(self):
        assert build_login_body("a b", "p&q") == "username=a+b&password=p%26q"

    def test_login_body_encodes_at_sign(self):
        # Kotlin oracle fixture: alice@example.com → %40, space → +, & → %26
        body = build_login_body("alice@example.com", "p@ss w&d")
        assert body == "username=alice%40example.com&password=p%40ss+w%26d"

    def test_catalogue_body_pins_horse_racing(self):
        body = json.loads(build_catalogue_body(
            market_type_codes=["WIN"], countries=["GB", "IE"],
            from_="2026-05-25T23:00:00Z", to="2026-05-26T23:00:00Z",
            projection=["EVENT"], max_results=1000, sort="FIRST_TO_START"))
        assert body["filter"]["eventTypeIds"] == ["7"]
        assert body["filter"]["marketTypeCodes"] == ["WIN"]
        assert body["filter"]["marketCountries"] == ["GB", "IE"]
        assert body["filter"]["marketStartTime"] == {
            "from": "2026-05-25T23:00:00Z", "to": "2026-05-26T23:00:00Z"}
        assert body["maxResults"] == "1000"
        assert body["sort"] == "FIRST_TO_START"

    def test_book_body(self):
        body = json.loads(build_book_body(["1.1", "1.2"]))
        assert body["marketIds"] == ["1.1", "1.2"]
        assert body["priceProjection"] == {"priceData": ["EX_BEST_OFFERS"]}

    def test_book_body_rejects_empty(self):
        with pytest.raises(ValueError, match="1..40"):
            build_book_body([])

    def test_book_body_rejects_over_40(self):
        with pytest.raises(ValueError, match="1..40"):
            build_book_body([f"1.{i}" for i in range(41)])
