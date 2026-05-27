"""Tests for cli.py: orchestration with a FakeSession injected.

No real browser. Covers happy path, partial failure, all-fail,
index-fail, bad args, empty day, region filtering, today window."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from paddypower_scraper import api, cli
from paddypower_scraper.browser import BrowserFetchError


# --- Test doubles ---

class FakeSession:
    """Returns canned dicts from a URL → payload map. Raises if a URL
    not in the map is requested. Use `errors` to register URLs that
    should raise BrowserFetchError instead."""

    def __init__(self, responses: dict[str, dict], errors: dict[str, str] | None = None):
        self.responses = responses
        self.errors = errors or {}
        self.calls: list[str] = []

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.calls.append(url)
        if url in self.errors:
            raise BrowserFetchError(url, self.errors[url])
        if url not in self.responses:
            raise AssertionError(f"unexpected URL in test: {url}")
        return self.responses[url]


def make_session_factory(session: FakeSession):
    @contextmanager
    def _factory():
        yield session
    return _factory


# --- Fixture data ---

def _index_payload(races: list[dict]) -> dict:
    return {"attachments": {"races": {r["raceId"]: r for r in races}}}


def _race_meta(*, race_id, meeting_id, win_market_id, start_time, country, venue):
    return {
        "raceId": race_id,
        "meetingId": meeting_id,
        "winMarketId": win_market_id,
        "startTime": start_time,
        "countryCode": country,
        "venue": venue,
    }


def _meeting_payload(race_id: str, win_market_id: str,
                     start_time: str, venue: str, country: str) -> dict:
    return {
        "races": {
            race_id: {
                "raceId": race_id,
                "winMarketId": win_market_id,
                "startTime": start_time,
                "venue": venue,
                "countryCode": country,
                "winMarketName": "Test Race",
            }
        },
        "markets": {
            win_market_id: {
                "marketName": "Test Race",
                "exchangeMarketId": f"1.exchange_{race_id}",
                "eachwayAvailable": True,
                "numberOfPlaces": 3,
                "placeFraction": {"numerator": 1, "denominator": 5},
                "runners": [
                    {"runnerName": "Horse A", "selectionId": 1, "runnerStatus": "ACTIVE",
                     "winRunnerOdds": {"trueOdds": {
                         "decimalOdds": {"decimalOdds": 4.0},
                         "fractionalOdds": {"numerator": 3, "denominator": 1},
                     }}},
                ],
            }
        },
    }


# --- Tests ---

NOW = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)


class TestHappyPath:
    def test_writes_paddypower_json(self, tmp_path: Path):
        index_race = _race_meta(
            race_id="100.1800", meeting_id="100", win_market_id="927.1",
            start_time="2026-05-26T18:00:00.000Z", country="GB", venue="Plumpton",
        )
        meeting = _meeting_payload("100.1800", "927.1",
                                   "2026-05-26T18:00:00.000Z", "Plumpton", "GB")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([index_race]),
            api.racing_page_url("100.1800"): meeting,
        }
        session = FakeSession(responses)
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["raceCount"] == 1
        assert data["races"][0]["venue"] == "Plumpton"


def _market_for(win_market_id: str, race_id: str) -> dict:
    return {
        win_market_id: {
            "marketName": "Test Race",
            "exchangeMarketId": f"1.exchange_{race_id}",
            "eachwayAvailable": True,
            "numberOfPlaces": 3,
            "placeFraction": {"numerator": 1, "denominator": 5},
            "runners": [
                {"runnerName": "Horse A", "selectionId": 1, "runnerStatus": "ACTIVE",
                 "winRunnerOdds": {"trueOdds": {
                     "decimalOdds": {"decimalOdds": 4.0},
                     "fractionalOdds": {"numerator": 3, "denominator": 1},
                 }}},
            ],
        }
    }


class TestPerRaceFanout:
    """A racing-page response lists the whole meeting's race metadata but
    includes the market for ONLY the requested raceId. The scraper must fan
    out per race to retrieve every race's market, not once per meeting."""

    def test_all_races_in_a_meeting_returned(self, tmp_path: Path):
        r1 = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                        start_time="2026-05-26T18:00:00.000Z", country="GB", venue="Plumpton")
        r2 = _race_meta(race_id="100.1830", meeting_id="100", win_market_id="927.2",
                        start_time="2026-05-26T18:30:00.000Z", country="GB", venue="Plumpton")
        # Every racing-page response carries BOTH race rows (whole meeting),
        # but markets only for the race whose raceId was requested.
        both_rows = {
            "100.1800": {"raceId": "100.1800", "winMarketId": "927.1",
                         "startTime": "2026-05-26T18:00:00.000Z", "venue": "Plumpton",
                         "countryCode": "GB", "winMarketName": "R1"},
            "100.1830": {"raceId": "100.1830", "winMarketId": "927.2",
                         "startTime": "2026-05-26T18:30:00.000Z", "venue": "Plumpton",
                         "countryCode": "GB", "winMarketName": "R2"},
        }
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([r1, r2]),
            api.racing_page_url("100.1800"): {"races": both_rows,
                                              "markets": _market_for("927.1", "100.1800")},
            api.racing_page_url("100.1830"): {"races": both_rows,
                                              "markets": _market_for("927.2", "100.1830")},
        }
        session = FakeSession(responses)
        out = tmp_path / "paddypower.json"
        rc = cli.main(["gb-ie"], now_utc=NOW,
                      make_session=make_session_factory(session), out_path=out)
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["raceCount"] == 2
        assert sorted(r["offTime"][11:16] for r in data["races"]) == ["19:00", "19:30"]
        # one racing-page call per race
        assert len([u for u in session.calls if "racing-page" in u]) == 2


class TestPartialFailure:
    def test_one_meeting_fails_rest_succeeds(self, tmp_path: Path):
        good = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        bad = _race_meta(race_id="200.1900", meeting_id="200", win_market_id="927.2",
                         start_time="2026-05-26T19:00:00.000Z", country="GB",
                         venue="Lingfield")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([good, bad]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        errors = {api.racing_page_url("200.1900"): "HTTP 500"}
        session = FakeSession(responses, errors)
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0  # partial success → 0
        data = json.loads(out.read_text())
        assert data["raceCount"] == 1
        assert data["races"][0]["venue"] == "Plumpton"


class TestAllMeetingsFail:
    def test_exits_one(self, tmp_path: Path):
        race = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        responses = {api.MEETINGS_INDEX_URL: _index_payload([race])}
        errors = {api.racing_page_url("100.1800"): "HTTP 503"}
        session = FakeSession(responses, errors)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1


class TestIndexFetchFails:
    def test_exits_one(self, tmp_path: Path):
        session = FakeSession({}, {api.MEETINGS_INDEX_URL: "HTTP 503"})
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1


class TestBadArgs:
    def test_unknown_region_exits_two(self, tmp_path: Path):
        session = FakeSession({})
        rc = cli.main(
            ["xx"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 2

    def test_default_region_is_gb_ie(self, tmp_path: Path):
        # No args → default 'gb-ie'. Index returns nothing → empty day path.
        session = FakeSession({api.MEETINGS_INDEX_URL: _index_payload([])})
        rc = cli.main(
            [],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0


class TestLegitimateEmptyDay:
    def test_writes_empty_output_exits_zero(self, tmp_path: Path):
        session = FakeSession({api.MEETINGS_INDEX_URL: _index_payload([])})
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data == {"scrapedAt": data["scrapedAt"], "raceCount": 0, "races": []}


class TestRegionFiltering:
    def test_us_race_excluded_from_gb_ie_run(self, tmp_path: Path):
        gb = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                        start_time="2026-05-26T18:00:00.000Z", country="GB",
                        venue="Plumpton")
        us = _race_meta(race_id="200.2200", meeting_id="200", win_market_id="927.2",
                        start_time="2026-05-26T22:00:00.000Z", country="US",
                        venue="Finger Lakes")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([gb, us]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0
        # Only Plumpton was fanned out; Finger Lakes filtered before fetch
        fanout_calls = [u for u in session.calls if "racing-page" in u]
        assert len(fanout_calls) == 1


class TestTodayWindowFiltering:
    def test_tomorrow_race_excluded(self, tmp_path: Path):
        today = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                           start_time="2026-05-26T18:00:00.000Z", country="GB",
                           venue="Plumpton")
        tomorrow = _race_meta(race_id="200.1800", meeting_id="200", win_market_id="927.2",
                              start_time="2026-05-27T18:00:00.000Z", country="GB",
                              venue="Lingfield")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([today, tomorrow]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0
        fanout_calls = [u for u in session.calls if "racing-page" in u]
        assert len(fanout_calls) == 1


class TestParseExceptionAllFail:
    def test_parse_exception_skips_meeting_exits_one(self, tmp_path: Path, monkeypatch):
        race = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([race]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }

        def _boom(payload, scraped_at):
            raise ValueError("unexpected structure")

        monkeypatch.setattr(cli, "parse_meeting_response", _boom)
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1


class TestAllMeetingsEmptyParse:
    def test_empty_parse_result_exits_one(self, tmp_path: Path):
        race = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        # Meeting whose WIN market has no usable runners → parse yields []
        meeting = {
            "races": {
                "100.1800": {
                    "raceId": "100.1800", "winMarketId": "927.1",
                    "startTime": "2026-05-26T18:00:00.000Z",
                    "venue": "Plumpton", "countryCode": "GB",
                    "winMarketName": "Test Race",
                }
            },
            "markets": {
                "927.1": {
                    "marketName": "Test Race",
                    "exchangeMarketId": "1.x",
                    "runners": [],  # no usable runners → race dropped → parse returns []
                }
            },
        }
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([race]),
            api.racing_page_url("100.1800"): meeting,
        }
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1
