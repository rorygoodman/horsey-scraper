"""Tests for arb_finder.validation (horses.json)."""

from __future__ import annotations

import json

from arb_finder.validation import validate_horses_output


def _valid() -> dict:
    return {
        "computedAt": "2026-05-27T20:34:11Z",
        "betfairScrapedAt": "2026-05-27T20:34:01Z",
        "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
        "horseCount": 1,
        "horses": [{
            "venue": "Finger Lakes", "country": "US",
            "offTime": "2026-05-27T21:47:00+01:00", "marketName": "21:47 Finger Lakes",
            "betfairWinMarketId": "1.258619108",
            "runner": {"name": "Emerald Forest", "selectionId": 12345678},
            "paddypower": {"winPrice": 2.88, "winPriceRaw": "15/8",
                           "eachWayTerms": {"fraction": 0.25, "places": 2}},
            "betfair": {"winLay": 2.92, "placeLay": 1.64, "placeMarket": "TOP_2"},
            "edge": -0.0599,
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_horses_output(json.dumps(p))


def test_valid_with_negative_edge():
    assert _v(_valid()) == []


def test_empty_horses_valid():
    p = {"computedAt": "2026-05-27T20:34:11Z",
         "betfairScrapedAt": "2026-05-27T20:34:01Z",
         "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
         "horseCount": 0, "horses": []}
    assert _v(p) == []


def test_not_json():
    errs = validate_horses_output("{bad")
    assert errs and "not valid JSON" in errs[0]


def test_horse_count_mismatch():
    p = _valid(); p["horseCount"] = 5
    assert any("horseCount" in e for e in _v(p))


def test_edge_not_number():
    p = _valid(); p["horses"][0]["edge"] = "lots"
    assert any("edge" in e for e in _v(p))


def test_missing_edge():
    p = _valid(); del p["horses"][0]["edge"]
    assert any("edge" in e for e in _v(p))


def test_bad_place_market():
    p = _valid(); p["horses"][0]["betfair"]["placeMarket"] = "TOP_9"
    assert any("placeMarket" in e for e in _v(p))


def test_place_lay_not_number():
    p = _valid(); p["horses"][0]["betfair"]["placeLay"] = "x"
    assert any("placeLay" in e for e in _v(p))


def test_eachway_places_out_of_range():
    p = _valid(); p["horses"][0]["paddypower"]["eachWayTerms"]["places"] = 6
    assert any("places must be in" in e for e in _v(p))


def test_missing_runner_selection_id():
    p = _valid(); del p["horses"][0]["runner"]["selectionId"]
    assert any("selectionId" in e for e in _v(p))


def test_bad_computed_at():
    p = _valid(); p["computedAt"] = "2026-05-27T18:00:00+01:00"  # offset, not a 'Z' instant
    assert any("computedAt is not ISO-8601 UTC" in e for e in _v(p))


def test_eachway_fraction_out_of_range():
    p = _valid(); p["horses"][0]["paddypower"]["eachWayTerms"]["fraction"] = 1.5
    assert any("fraction must be in (0,1]" in e for e in _v(p))


def test_missing_venue():
    p = _valid(); del p["horses"][0]["venue"]
    assert any("venue" in e for e in _v(p))
