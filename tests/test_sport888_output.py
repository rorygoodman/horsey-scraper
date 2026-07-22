import json

from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from sport888_scraper.output import write_sport888_json


def _out() -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:00Z",
        race_count=1,
        races=[Sport888Race(
            venue="Worcester", country="uk-and-ireland",
            off_time="2026-07-22T12:55:00+00:00", market_name="Winner Market",
            scraped_at="2026-07-22T12:00:00Z",
            each_way_terms=EachWayTerms(0.2, 3),
            runners=[Sport888Runner("Holy Legend", 3.25, "9/4")],
        )],
    )


def test_writes_camelcase(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["offTime"] == "2026-07-22T12:55:00+00:00"
    assert race["marketName"] == "Winner Market"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    r = race["runners"][0]
    assert r["winPrice"] == 3.25 and r["winPriceRaw"] == "9/4"


def test_no_betfair_ids_in_output(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_out(), p)
    text = p.read_text()
    assert "betfair" not in text.lower()
    assert "selectionId" not in text
