import copy

from sport888_scraper.models import Sport888Stub
from sport888_scraper.schedule import parse_schedule


class TestParseSchedule:
    def test_returns_stubs(self, eight88_schedule_payload):
        stubs = parse_schedule(eight88_schedule_payload)
        assert stubs, "fixture should yield stubs"
        assert all(isinstance(s, Sport888Stub) for s in stubs)

    def test_includes_uk_and_ireland(self, eight88_schedule_payload):
        stubs = parse_schedule(eight88_schedule_payload)
        slugs = {s.category_slug for s in stubs}
        assert "uk-and-ireland" in slugs
        worcester = [s for s in stubs if s.venue == "Worcester"]
        assert worcester
        assert worcester[0].start_time_utc.startswith("2026-07-22T")
        assert worcester[0].event_id  # non-empty

    def test_field_types(self, eight88_schedule_payload):
        for s in parse_schedule(eight88_schedule_payload):
            for f in ("event_id", "venue", "category_slug", "start_time_utc"):
                v = getattr(s, f)
                assert isinstance(v, str) and v, f"{f} bad: {v!r}"

    def test_drops_entry_missing_scheduled_start(self, eight88_schedule_payload):
        p = copy.deepcopy(eight88_schedule_payload)
        victim = next(iter(p["event_details"]))
        p["event_details"][victim].pop("scheduled_start", None)
        stubs = parse_schedule(p)
        assert all(s.event_id != str(victim) for s in stubs)

    def test_empty_payload(self):
        assert parse_schedule({}) == []
        assert parse_schedule({"event_details": {}}) == []

    def test_returns_list(self, eight88_schedule_payload):
        assert isinstance(parse_schedule(eight88_schedule_payload), list)
