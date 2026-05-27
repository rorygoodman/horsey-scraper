"""Tests for arb_finder.validation."""

from __future__ import annotations

import json

from arb_finder.validation import validate_arbs_output


def _valid() -> dict:
    return {
        "computedAt": "2026-05-25T17:06:08.398333Z",
        "betfairScrapedAt": "2026-05-25T17:05:56.890289Z",
        "paddypowerScrapedAt": "2026-05-25T17:05:58.384555Z",
        "arbCount": 1,
        "arbs": [{
            "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "marketName": "18:00 Ascot",
            "betfairWinMarketId": "1.1",
            "runner": {"name": "A", "selectionId": 1},
            "paddypower": {"winPrice": 3.0, "winPriceRaw": "2/1",
                           "eachWayTerms": {"fraction": 0.2, "places": 2}},
            "betfair": {"winLay": 2.0, "topNLay": 1.4, "topNType": "TOP_2"},
            "margin": 0.25,
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_arbs_output(json.dumps(p))


def test_valid():
    assert _v(_valid()) == []


def test_empty_arbs_valid():
    p = {"computedAt": "2026-05-25T17:06:08Z",
         "betfairScrapedAt": "2026-05-25T17:05:56Z",
         "paddypowerScrapedAt": "2026-05-25T17:05:58Z",
         "arbCount": 0, "arbs": []}
    assert _v(p) == []


def test_arb_count_mismatch():
    p = _valid(); p["arbCount"] = 5
    assert any("arbCount" in e for e in _v(p))


def test_margin_must_be_positive():
    p = _valid(); p["arbs"][0]["margin"] = 0
    assert any("margin must be > 0" in e for e in _v(p))


def test_bad_topn_type():
    p = _valid(); p["arbs"][0]["betfair"]["topNType"] = "TOP_9"
    assert any("topNType" in e for e in _v(p))


def test_eachway_places_out_of_range():
    p = _valid(); p["arbs"][0]["paddypower"]["eachWayTerms"]["places"] = 6
    assert any("places must be in" in e for e in _v(p))


def test_missing_runner_selection_id():
    p = _valid(); del p["arbs"][0]["runner"]["selectionId"]
    assert any("selectionId" in e for e in _v(p))


# --- Additional tests from oracle (Step 5) ---

def test_margin_negative():
    """Oracle: margin negative is flagged (not just zero)."""
    p = _valid(); p["arbs"][0]["margin"] = -0.05
    assert any("margin" in e for e in _v(p))


def test_non_iso_computed_at():
    """Oracle: non-ISO computedAt is flagged with 'ISO-8601' in message."""
    p = _valid(); p["computedAt"] = "yesterday"
    errs = _v(p)
    assert any("computedAt" in e and "ISO-8601" in e for e in errs)


def test_ew_fraction_out_of_range():
    """Oracle: EW fraction > 1.0 is flagged."""
    p = _valid(); p["arbs"][0]["paddypower"]["eachWayTerms"]["fraction"] = 1.5
    assert any("fraction" in e for e in _v(p))


def test_missing_venue():
    """Oracle: missing required arb field (venue) is flagged."""
    p = _valid(); del p["arbs"][0]["venue"]
    assert any("venue" in e for e in _v(p))


def test_not_valid_json():
    """Implementation handles non-JSON input gracefully."""
    errs = validate_arbs_output("not json at all")
    assert any("not valid JSON" in e for e in errs)
