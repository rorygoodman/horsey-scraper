from novibet_scraper.models import NovibetStub
from novibet_scraper.overview import parse_overview


class TestParseOverview:
    def test_returns_every_race_across_both_days(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        # 59 races on Jul 31 + 17 on Aug 01
        assert len(stubs) == 76
        assert all(isinstance(s, NovibetStub) for s in stubs)

    def test_first_stub_carries_id_venue_country_and_time(
            self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        first = next(s for s in stubs if s.bet_context_id == "47383594")
        assert first.venue == "Goodwood"
        assert first.country == "GB"
        assert first.start_time_utc == "2026-07-31T12:50:00+00:00"

    def test_bet_context_id_is_a_string(self, novibet_overview_payload):
        # The feed sends it as an int; the racecard URL builder needs a str.
        stubs = parse_overview(novibet_overview_payload)
        assert all(isinstance(s.bet_context_id, str) for s in stubs)

    def test_country_captions_are_novibets_own(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        assert {"GB", "IRE", "USA", "SAF", "GER", "AUS"} >= {
            s.country for s in stubs}

    def test_gb_day_one_count(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        gb_today = [s for s in stubs
                    if s.country == "GB" and s.start_time_utc.startswith("2026-07-31")]
        assert len(gb_today) == 41

    def test_empty_and_malformed_payloads_yield_nothing(self):
        assert parse_overview({}) == []
        assert parse_overview({"days": None}) == []
        assert parse_overview({"days": [{"countries": [{"meetings": [{}]}]}]}) == []

    def test_incomplete_entries_are_dropped(self):
        payload = {"days": [{"countries": [{"caption": "GB", "meetings": [{
            "caption": "Goodwood",
            "races": [
                {"betContextId": 1, "startTimeUTC": "2026-07-31T12:50:00+00:00"},
                {"betContextId": 2},                       # no start time
                {"startTimeUTC": "2026-07-31T13:00:00+00:00"},  # no id
            ]}]}]}]}
        stubs = parse_overview(payload)
        assert [s.bet_context_id for s in stubs] == ["1"]
