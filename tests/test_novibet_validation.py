import json

from novibet_scraper.validation import validate_novibet_output

GOOD = {
    "scrapedAt": "2026-07-31T12:00:00Z",
    "raceCount": 1,
    "races": [{
        "venue": "Wolverhampton", "country": "GB",
        "offTime": "2026-07-31T13:00:00+00:00", "marketName": "Race Winner",
        "scrapedAt": "2026-07-31T12:00:00Z",
        "eachWayTerms": {"fraction": 0.2, "places": 3},
        "runners": [{"name": "Marianne Mozart",
                     "winPrice": 15.0, "winPriceRaw": "14/1"}],
    }],
}


def _errs(mutate=None):
    payload = json.loads(json.dumps(GOOD))
    if mutate:
        mutate(payload)
    return validate_novibet_output(json.dumps(payload))


def test_good_payload_has_no_errors():
    assert _errs() == []


def test_not_json():
    assert validate_novibet_output("not json")


def test_race_count_must_match():
    assert any("raceCount" in e for e in _errs(
        lambda p: p.update(raceCount=7)))


def test_off_time_must_carry_an_offset():
    assert any("offTime" in e for e in _errs(
        lambda p: p["races"][0].update(offTime="2026-07-31T13:00:00")))


def test_six_places_is_accepted():
    # Novibet runs 6-place boosts; novibet.json records them even though the
    # arb step cannot price them (Betfair stops at TOP_5).
    assert _errs(lambda p: p["races"][0]["eachWayTerms"].update(places=6)) == []


def test_zero_places_is_rejected():
    assert any("places" in e for e in _errs(
        lambda p: p["races"][0]["eachWayTerms"].update(places=0)))


def test_fraction_out_of_range_is_rejected():
    assert any("fraction" in e for e in _errs(
        lambda p: p["races"][0]["eachWayTerms"].update(fraction=1.5)))


def test_null_each_way_terms_is_allowed():
    assert _errs(lambda p: p["races"][0].update(eachWayTerms=None)) == []


def test_price_parity_is_enforced():
    assert any("parity" in e for e in _errs(
        lambda p: p["races"][0]["runners"][0].update(winPriceRaw=None)))
