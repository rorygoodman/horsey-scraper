import json

from williamhill_scraper.validation import validate_williamhill_output


def _doc(**race_overrides):
    race = {
        "venue": "Warwick", "country": "uk-ireland",
        "offTime": "2026-11-03T15:48:00Z", "marketName": "Win",
        "scrapedAt": "2026-11-03T12:00:01Z",
        "eachWayTerms": {"fraction": 0.2, "places": 3},
        "runners": [{"name": "Ballymoreen", "winPrice": 3.5, "winPriceRaw": "5/2"}],
    }
    race.update(race_overrides)
    return json.dumps({"scrapedAt": "2026-11-03T12:00:00Z", "raceCount": 1,
                       "races": [race]})


def test_valid():
    assert validate_williamhill_output(_doc()) == []


def test_null_terms_are_valid():
    assert validate_williamhill_output(_doc(eachWayTerms=None)) == []


def test_price_parity_enforced():
    bad = _doc(runners=[{"name": "X", "winPrice": 3.5, "winPriceRaw": None}])
    assert any("parity" in e for e in validate_williamhill_output(bad))
