import json

from novibet_scraper.models import (
    EachWayTerms, NovibetOutput, NovibetRace, NovibetRunner,
)
from novibet_scraper.output import write_novibet_json
from novibet_scraper.validation import validate_novibet_output


def _out() -> NovibetOutput:
    return NovibetOutput(
        scraped_at="2026-07-31T12:00:00Z",
        race_count=1,
        races=[NovibetRace(
            venue="Wolverhampton", country="GB",
            off_time="2026-07-31T13:00:00+00:00", market_name="Race Winner",
            scraped_at="2026-07-31T12:00:00Z",
            each_way_terms=EachWayTerms(fraction=0.2, places=3),
            runners=[NovibetRunner("Marianne Mozart", 15.0, "14/1"),
                     NovibetRunner("Suspended", None, None)])],
    )


def test_writes_camel_case(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["scrapedAt"] == "2026-07-31T12:00:00Z"
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["offTime"] == "2026-07-31T13:00:00+00:00"
    assert race["marketName"] == "Race Winner"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    assert race["runners"][0] == {"name": "Marianne Mozart",
                                  "winPrice": 15.0, "winPriceRaw": "14/1"}
    assert race["runners"][1] == {"name": "Suspended",
                                  "winPrice": None, "winPriceRaw": None}


def test_written_output_validates(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(_out(), p)
    assert validate_novibet_output(p.read_text()) == []


def test_empty_output_validates(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(NovibetOutput("2026-07-31T12:00:00Z", 0, []), p)
    assert validate_novibet_output(p.read_text()) == []
