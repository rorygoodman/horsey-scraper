from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sport888_scraper import api, cli
from sport888_scraper.browser import BrowserFetchError


class FakeSession:
    def __init__(self, responses, errors=None):
        self.responses = responses
        self.errors = errors or {}
        self.calls: list[str] = []

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.calls.append(url)
        if url in self.errors:
            raise BrowserFetchError(url, self.errors[url])
        if url not in self.responses:
            raise AssertionError(f"unexpected URL: {url}")
        return self.responses[url]


def make_factory(session):
    @contextmanager
    def _factory():
        yield session
    return _factory


NOW = datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc)


def _schedule(events: list[dict]) -> dict:
    return {"event_details": {e["id"]: e for e in events}}


def _event(eid, name, slug, start):
    return {"id": eid, "name": name, "category_slug": slug,
            "scheduled_start": start}


def _racecard(eid, name, slug, start, runners):
    return {"racecard": {
        "events": {eid: {"details": {
            "id": eid, "name": name, "category_slug": slug,
            "scheduled_start": start}}},
        "each_way_terms": {eid: {"allow_each_way": "1",
                                 "place_odds_divisor": "5", "places_paid": "3"}},
        "selections_details": {
            f"{eid}_{i}": {"name": rn, "market_id": "1", "active": "1",
                           "betable": True, "decimal_price": "4.000",
                           "fraction_price": "3/1"}
            for i, rn in enumerate(runners)},
    }}


def test_happy_path_writes_json(tmp_path: Path):
    ev = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([ev]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], now_utc=NOW,
                  make_session=make_factory(FakeSession(responses)), out_path=out)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 1
    assert data["races"][0]["venue"] == "Worcester"
    assert data["races"][0]["runners"][0]["name"] == "Holy Legend"


def test_region_filter_excludes_us_from_gb_ie(tmp_path: Path):
    gb = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    us = _event("222", "Belmont", "north-america", "2026-07-22T20:00:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([gb, us]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    session = FakeSession(responses)
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 0
    assert [u for u in session.calls if "getRacecard" in u] == [api.racecard_url("111")]


def test_index_fetch_fails_exits_1(tmp_path: Path):
    session = FakeSession({}, {api.SCHEDULE_URL: "HTTP 503"})
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 1


def test_empty_day_writes_empty_exits_0(tmp_path: Path):
    session = FakeSession({api.SCHEDULE_URL: _schedule([])})
    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=out)
    assert rc == 0
    assert json.loads(out.read_text())["raceCount"] == 0


def test_all_races_fail_exits_1(tmp_path: Path):
    ev = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    session = FakeSession({api.SCHEDULE_URL: _schedule([ev])},
                          {api.racecard_url("111"): "HTTP 500"})
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 1


def test_bad_region_exits_2(tmp_path: Path):
    session = FakeSession({})
    rc = cli.main(["xx"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 2


def test_tomorrow_race_excluded(tmp_path: Path):
    today = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    tomorrow = _event("222", "Naas", "uk-and-ireland", "2026-07-23T18:00:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([today, tomorrow]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    session = FakeSession(responses)
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 0
    assert [u for u in session.calls if "getRacecard" in u] == [api.racecard_url("111")]
