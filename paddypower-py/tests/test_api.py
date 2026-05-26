"""Tests for api.py: URL constants and per-race URL builder."""

from urllib.parse import parse_qs, urlparse

from paddypower_scraper.api import (
    LOCALE,
    MEETINGS_INDEX_URL,
    TIMEZONE,
    USER_AGENT,
    WARMUP_URL,
    racing_page_url,
)


def _qs(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


class TestMeetingsIndexUrl:
    def test_targets_content_managed_page_v7(self):
        u = urlparse(MEETINGS_INDEX_URL)
        assert u.netloc == "apisms.paddypower.com"
        assert u.path == "/smspp/content-managed-page/v7"

    def test_cards_to_fetch_is_63(self):
        assert _qs(MEETINGS_INDEX_URL)["cardsToFetch"] == ["63"]

    def test_has_required_params(self):
        qs = _qs(MEETINGS_INDEX_URL)
        for key in (
            "_ak",
            "betexRegion",
            "countryCode",
            "eventTypeId",
            "includePrices",
            "language",
            "page",
            "regionCode",
            "timezone",
        ):
            assert key in qs, f"missing query param: {key}"

    def test_event_type_id_is_7(self):
        # 7 = horse racing in PaddyPower's taxonomy
        assert _qs(MEETINGS_INDEX_URL)["eventTypeId"] == ["7"]


class TestRacingPageUrl:
    def test_basic_shape(self):
        url = racing_page_url("35646567.1800")
        u = urlparse(url)
        assert u.netloc == "apisms.paddypower.com"
        assert u.path == "/smspp/racing-page/v7"
        assert _qs(url)["raceId"] == ["35646567.1800"]

    def test_includes_prices(self):
        assert _qs(racing_page_url("1.2"))["includePrices"] == ["true"]

    def test_race_id_with_dot_round_trips(self):
        # PaddyPower race ids contain a dot; ensure it survives URL encoding
        assert _qs(racing_page_url("35646567.1800"))["raceId"] == ["35646567.1800"]


class TestConstants:
    def test_warmup_url_is_horse_racing_landing(self):
        assert WARMUP_URL == "https://www.paddypower.com/horse-racing"

    def test_user_agent_is_chrome_like(self):
        assert "Chrome" in USER_AGENT
        assert "Mozilla" in USER_AGENT

    def test_locale_en_gb(self):
        assert LOCALE == "en-GB"

    def test_timezone_dublin(self):
        # Matches PaddyPower's regional API context — see Kotlin PaddyClient
        assert TIMEZONE == "Europe/Dublin"
