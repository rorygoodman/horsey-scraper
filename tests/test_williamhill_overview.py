from williamhill_scraper.models import WilliamHillStub
from williamhill_scraper.overview import parse_day_index
from conftest import mutate  # repo convention: tests/ is not a package


def test_parses_every_region(williamhill_day_index_payload):
    # The fixture's virtual-racing events had already run (settled=true).
    stubs = parse_day_index(williamhill_day_index_payload)
    assert {s.country for s in stubs} == {"uk-ireland", "us-canada", "europe"}
    assert len(stubs) == 16


def test_stub_fields(williamhill_day_index_payload):
    stubs = parse_day_index(williamhill_day_index_payload)
    assert stubs[0] == WilliamHillStub(
        event_id="OB_EV41748423", venue="Warwick", country="uk-ireland",
        start_time_utc="2026-11-03T12:18:00Z")


def test_drops_settled_events(williamhill_day_index_payload):
    p = mutate(williamhill_day_index_payload)
    p["regionCompetitions"][0]["competitions"][0]["events"][0]["settled"] = True
    ids = {s.event_id for s in parse_day_index(p)}
    assert "OB_EV41748423" not in ids


def test_drops_abandoned_meetings(williamhill_day_index_payload):
    p = mutate(williamhill_day_index_payload)
    p["regionCompetitions"][0]["competitions"][0]["competition"]["_abandoned"] = True
    assert "Warwick" not in {s.venue for s in parse_day_index(p)}


def test_drops_malformed_events(williamhill_day_index_payload):
    p = mutate(williamhill_day_index_payload)
    events = p["regionCompetitions"][0]["competitions"][0]["events"]
    events[0]["startDateTime"] = "soon"
    del events[1]["id"]
    assert len(parse_day_index(p)) == 14


def test_garbage_payloads_yield_nothing():
    for bad in (None, [], {}, {"regionCompetitions": "x"},
                {"regionCompetitions": [{"regionFilter": {}}]}):
        assert parse_day_index(bad) == []
