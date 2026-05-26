"""Tests for betfair_scraper.validation."""

from __future__ import annotations

import json

from betfair_scraper.validation import validate_scrape_output


def _valid() -> dict:
    return {
        "scrapedAt": "2026-05-25T17:05:56.890289Z",
        "raceCount": 1,
        "races": [{
            "raceId": "1.258528220", "venue": "Ballinrobe", "country": "IE",
            "offTime": "2026-05-25T18:05:00+01:00",
            "winMarketUrl": "https://x/market/1.258528220",
            "marketName": "18:05 Ballinrobe",
            "marketScrapedAt": {"WIN": "2026-05-25T17:05:58.303431Z"},
            "runners": [
                {"name": "A", "lay": {"WIN": 2.5}, "selectionId": 1},
                {"name": "B", "lay": {"WIN": None}, "selectionId": None},
            ],
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_scrape_output(json.dumps(p))


def test_valid():
    assert _v(_valid()) == []


def test_not_json():
    errs = validate_scrape_output("{bad")
    assert errs and "not valid JSON" in errs[0]


def test_race_count_mismatch():
    p = _valid(); p["raceCount"] = 9
    assert any("raceCount" in e for e in _v(p))


def test_bad_race_id():
    p = _valid(); p["races"][0]["raceId"] = "2.999"
    assert any("raceId does not match" in e for e in _v(p))


def test_race_id_trailing_newline_rejected():
    # fullmatch (not match): a trailing newline must NOT pass ^1\.\d+$.
    p = _valid(); p["races"][0]["raceId"] = "1.123\n"
    assert any("raceId does not match" in e for e in _v(p))


def test_bad_country():
    p = _valid(); p["races"][0]["country"] = "FR"
    assert any("country not in" in e for e in _v(p))


def test_bad_offtime():
    p = _valid(); p["races"][0]["offTime"] = "2026-05-25T18:05:00"
    assert any("offTime not ISO-8601 with offset" in e for e in _v(p))


def test_missing_win_key():
    p = _valid()
    p["races"][0]["marketScrapedAt"] = {"TOP_2": "2026-05-25T17:05:58.303431Z"}
    p["races"][0]["runners"] = [{"name": "A", "lay": {"TOP_2": 1.5}, "selectionId": 1}]
    assert any("missing required WIN key" in e for e in _v(p))


def test_unknown_market():
    p = _valid()
    p["races"][0]["marketScrapedAt"]["TOP_9"] = "2026-05-25T17:05:58.303431Z"
    assert any("unknown market" in e for e in _v(p))


def test_lay_key_parity_violation():
    p = _valid()
    p["races"][0]["runners"][0]["lay"] = {"WIN": 2.5, "TOP_2": 1.5}
    assert any("key parity violation" in e for e in _v(p))


def test_selection_id_not_number():
    p = _valid(); p["races"][0]["runners"][0]["selectionId"] = "1"
    assert any("selectionId: not a number" in e for e in _v(p))


# --- Step 5: extra tests from oracle (SchemaValidatorTest.kt) ---

def test_partial_markets_valid_when_parity_holds():
    """partial markets pass when key parity holds (oracle: partial markets test)."""
    p = _valid()
    p["races"][0]["marketScrapedAt"] = {
        "WIN": "2026-05-25T17:05:58.303431Z",
        "TOP_3": "2026-05-25T17:05:59.000000Z",
    }
    p["races"][0]["runners"] = [
        {"name": "X", "lay": {"WIN": 4.8, "TOP_3": 1.7}},
    ]
    assert _v(p) == []


def test_country_us_accepted():
    """US is an allowed country (oracle: accepts country US)."""
    p = _valid(); p["races"][0]["country"] = "US"
    assert _v(p) == []


def test_bad_scraped_at():
    """Bad scrapedAt format is flagged (oracle: bad scrapedAt format is flagged)."""
    p = _valid(); p["scrapedAt"] = "yesterday"
    assert any("scrapedAt" in e for e in _v(p))


def test_selection_id_present_and_numeric_accepted():
    """selectionId present and numeric is accepted (oracle: selectionId numeric)."""
    p = _valid(); p["races"][0]["runners"][0]["selectionId"] = 12345
    assert _v(p) == []
