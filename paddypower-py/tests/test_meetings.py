"""Tests for meetings.py: parsing the card-63 meetings index payload."""

from paddypower_scraper.meetings import parse_meetings_index
from paddypower_scraper.models import RaceStub

from .conftest import mutate


class TestParseMeetingsIndex:
    def test_returns_race_stubs(self, card63_payload):
        stubs = parse_meetings_index(card63_payload)
        assert len(stubs) > 100, "fixture should have hundreds of races"
        assert all(isinstance(s, RaceStub) for s in stubs)

    def test_stub_field_mapping(self, card63_payload):
        stubs = parse_meetings_index(card63_payload)
        first = stubs[0]
        # Every required field must be a non-empty string
        for field in ("race_id", "meeting_id", "win_market_id",
                      "start_time_utc", "country_code", "venue"):
            value = getattr(first, field)
            assert isinstance(value, str), f"{field} is {type(value).__name__}"
            assert value, f"{field} is empty"

    def test_drops_race_missing_country(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("countryCode", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_drops_race_missing_win_market_id(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("winMarketId", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_drops_race_missing_start_time(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("startTime", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_empty_attachments(self):
        assert parse_meetings_index({}) == []
        assert parse_meetings_index({"attachments": {}}) == []
        assert parse_meetings_index({"attachments": {"races": {}}}) == []

    def test_returns_list_not_generator(self, card63_payload):
        result = parse_meetings_index(card63_payload)
        assert isinstance(result, list)
