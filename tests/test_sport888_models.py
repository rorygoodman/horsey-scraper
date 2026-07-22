from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)


def _sample() -> dict:
    return {
        "scrapedAt": "2026-07-22T12:00:00Z",
        "raceCount": 1,
        "races": [
            {
                "venue": "Worcester",
                "country": "uk-and-ireland",
                "offTime": "2026-07-22T12:55:00+00:00",
                "marketName": "Winner Market",
                "scrapedAt": "2026-07-22T12:00:00Z",
                "eachWayTerms": {"fraction": 0.2, "places": 3},
                "runners": [
                    {"name": "Holy Legend", "winPrice": 3.25, "winPriceRaw": "9/4"},
                    {"name": "No Price", "winPrice": None, "winPriceRaw": None},
                ],
            }
        ],
    }


def test_from_dict_roundtrips_fields():
    out = Sport888Output.from_dict(_sample())
    assert out.race_count == 1
    race = out.races[0]
    assert isinstance(race, Sport888Race)
    assert race.venue == "Worcester"
    assert race.country == "uk-and-ireland"
    assert race.off_time == "2026-07-22T12:55:00+00:00"
    assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)
    assert race.runners[0] == Sport888Runner("Holy Legend", 3.25, "9/4")
    assert race.runners[1] == Sport888Runner("No Price", None, None)


def test_from_dict_null_each_way_terms():
    d = _sample()
    d["races"][0]["eachWayTerms"] = None
    assert Sport888Output.from_dict(d).races[0].each_way_terms is None
