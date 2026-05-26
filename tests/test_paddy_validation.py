"""Tests for the PaddyPower schema validator (port of PaddySchemaValidator.kt)."""

from __future__ import annotations

import json

from paddypower_scraper.validation import validate_paddy_output


def _valid() -> dict:
    return {
        "scrapedAt": "2026-05-25T17:05:58.384555Z",
        "raceCount": 1,
        "races": [
            {
                "venue": "Ballinrobe",
                "country": "IE",
                "offTime": "2026-05-25T18:05:00+01:00",
                "marketName": "18:05 Ballinrobe",
                "raceUrl": "https://www.paddypower.com/...",
                "scrapedAt": "2026-05-25T17:05:58.384555Z",
                "betfairWinMarketId": "1.258528220",
                "eachWayTerms": {"fraction": 0.2, "places": 3},
                "runners": [
                    {"name": "Sony Bill", "selectionId": 66986352,
                     "winPrice": 2.72, "winPriceRaw": "7/4"},
                    {"name": "Spare", "selectionId": None,
                     "winPrice": None, "winPriceRaw": None},
                ],
            }
        ],
    }


def _v(payload: dict) -> list[str]:
    return validate_paddy_output(json.dumps(payload))


class TestValid:
    def test_clean_payload(self):
        assert _v(_valid()) == []

    def test_null_eachway_ok(self):
        p = _valid()
        p["races"][0]["eachWayTerms"] = None
        assert _v(p) == []


class TestTopLevel:
    def test_not_json(self):
        errs = validate_paddy_output("{not json")
        assert errs and "not valid JSON" in errs[0]

    def test_missing_scraped_at(self):
        p = _valid(); del p["scrapedAt"]
        assert any("scrapedAt" in e for e in _v(p))

    def test_bad_scraped_at(self):
        p = _valid(); p["scrapedAt"] = "2026-05-25T18:05:00+01:00"
        assert any("scrapedAt is not ISO-8601 UTC" in e for e in _v(p))

    def test_race_count_mismatch(self):
        p = _valid(); p["raceCount"] = 5
        assert any("raceCount" in e for e in _v(p))


class TestRace:
    def test_bad_offtime(self):
        p = _valid(); p["races"][0]["offTime"] = "2026-05-25T18:05:00"
        assert any("offTime not ISO-8601 with offset" in e for e in _v(p))

    def test_bad_race_scraped_at(self):
        p = _valid(); p["races"][0]["scrapedAt"] = "nope"
        assert any("scrapedAt not ISO-8601 UTC" in e for e in _v(p))

    def test_eachway_fraction_out_of_range(self):
        p = _valid(); p["races"][0]["eachWayTerms"]["fraction"] = 0
        assert any("fraction must be in (0,1]" in e for e in _v(p))

    def test_eachway_places_out_of_range(self):
        p = _valid(); p["races"][0]["eachWayTerms"]["places"] = 7
        assert any("places must be in" in e for e in _v(p))


class TestRunner:
    def test_price_parity_violation(self):
        p = _valid()
        p["races"][0]["runners"][0]["winPriceRaw"] = None  # price set, raw null
        assert any("price parity violation" in e for e in _v(p))

    def test_price_parity_violation_raw_set_price_null(self):
        # Kotlin oracle: "price parity violation flagged when winPrice null but raw set"
        p = _valid()
        p["races"][0]["runners"][1]["winPriceRaw"] = "9/2"  # raw set, winPrice null
        assert any("parity" in e for e in _v(p))

    def test_win_price_not_number(self):
        p = _valid(); p["races"][0]["runners"][0]["winPrice"] = "2.72"
        assert any("winPrice" in e for e in _v(p))

    def test_missing_name(self):
        p = _valid(); del p["races"][0]["runners"][0]["name"]
        assert any("name" in e for e in _v(p))


class TestBoundary:
    def test_empty_races_zero_count_validates(self):
        # Kotlin oracle: "empty races array with zero raceCount validates"
        payload = {
            "scrapedAt": "2026-05-13T20:30:00Z",
            "raceCount": 0,
            "races": [],
        }
        assert validate_paddy_output(json.dumps(payload)) == []
