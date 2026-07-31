"""CLI orchestration for the Novibet scraper, with a stubbed session."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from novibet_scraper import api, cli
from novibet_scraper.browser import BrowserFetchError

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


class _StubSession:
    """Serves the committed fixtures by URL."""

    def __init__(self, racecards: dict, fail_index: bool = False):
        self.racecards = racecards
        self.fail_index = fail_index
        self.fetched: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.fetched.append(url)
        if url == api.OVERVIEW_URL:
            if self.fail_index:
                raise BrowserFetchError(url, "HTTP 403")
            return self.overview
        for bcid, payload in self.racecards.items():
            if f"/{bcid}" in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise BrowserFetchError(url, "HTTP 404")


def _run(session, tmp_path, argv=None):
    out = tmp_path / "novibet.json"
    rc = cli.main(argv if argv is not None else ["gb-ie"],
                  now_utc=NOW, make_session=lambda: session, out_path=out)
    return rc, out


def test_bad_region_exits_2(tmp_path):
    rc, _ = _run(_StubSession({}), tmp_path, ["atlantis"])
    assert rc == 2


def test_index_failure_exits_1(tmp_path, novibet_overview_payload):
    s = _StubSession({}, fail_index=True)
    s.overview = novibet_overview_payload
    rc, _ = _run(s, tmp_path)
    assert rc == 1


def test_writes_races_for_the_selected_region(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    rc, out = _run(s, tmp_path)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["venue"] == "Wolverhampton"
    assert race["country"] == "GB"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}


def test_only_in_region_races_are_fetched(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    _run(s, tmp_path)
    # SAF/GER meetings exist in the fixture and must never be requested.
    # These are the four Fairview (SAF) betContextIds in novibet_overview.json.
    saf_ids = ("47381068", "47381069", "47381070", "47381071")
    assert not [u for u in s.fetched if any(f"/{i}" in u for i in saf_ids)]


def test_empty_day_writes_empty_output_and_exits_0(tmp_path):
    s = _StubSession({})
    s.overview = {"days": []}
    rc, out = _run(s, tmp_path)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 0 and data["races"] == []


def test_all_races_failing_exits_1(tmp_path, novibet_overview_payload):
    s = _StubSession({})  # every racecard 404s
    s.overview = novibet_overview_payload
    rc, _ = _run(s, tmp_path)
    assert rc == 1


def test_partial_failure_still_writes_and_exits_0(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    rc, out = _run(s, tmp_path)
    assert rc == 0
    assert json.loads(out.read_text())["raceCount"] == 1
