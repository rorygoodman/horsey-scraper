"""CLI orchestration for the William Hill scraper, with a stubbed session."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from williamhill_scraper import api, cli
from williamhill_scraper.client import FetchError
from williamhill_scraper.validation import validate_williamhill_output

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


class _StubSession:
    """Serves the committed fixtures by URL."""

    def __init__(self, index, racecards: dict, fail_index: bool = False):
        self.index = index
        self.racecards = racecards
        self.fail_index = fail_index
        self.fetched: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.fetched.append(url)
        if url == api.DAY_INDEX_URL:
            if self.fail_index:
                raise FetchError(url, "HTTP 503")
            return self.index
        for eid, payload in self.racecards.items():
            if url == api.event_url(eid):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise FetchError(url, "HTTP 404")


def _run(session, tmp_path, argv=None):
    out = tmp_path / "williamhill.json"
    rc = cli.main(argv if argv is not None else ["gb-ie"],
                  now_utc=NOW, make_session=lambda: session, out_path=out)
    return rc, out


def test_bad_region_exits_2(tmp_path):
    rc, _ = _run(_StubSession({}, {}), tmp_path, ["atlantis"])
    assert rc == 2


def test_index_failure_exits_1(tmp_path, williamhill_day_index_payload):
    rc, _ = _run(_StubSession(williamhill_day_index_payload, {}, fail_index=True),
                 tmp_path)
    assert rc == 1


def test_writes_valid_output_for_the_selected_region(
        tmp_path, williamhill_day_index_payload, williamhill_racecard_3pl,
        williamhill_racecard_at_off):
    s = _StubSession(williamhill_day_index_payload, {
        "OB_EV41748423": williamhill_racecard_at_off,  # skipped: at the off
        "OB_EV41748412": williamhill_racecard_3pl,
    })
    rc, out = _run(s, tmp_path)
    assert rc == 0
    text = out.read_text()
    assert validate_williamhill_output(text) == []
    data = json.loads(text)
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["venue"] == "Warwick"
    assert race["country"] == "uk-ireland"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    assert race["runners"][0] == {
        "name": "An Buachaill Rua", "winPrice": 11.0, "winPriceRaw": "10/1"}


def test_only_in_region_races_are_fetched(
        tmp_path, williamhill_day_index_payload, williamhill_racecard_3pl):
    s = _StubSession(williamhill_day_index_payload,
                     {"OB_EV41748412": williamhill_racecard_3pl})
    _run(s, tmp_path)
    fetched = set(s.fetched) - {api.DAY_INDEX_URL}
    assert len(fetched) == 8  # Warwick + Sedgefield, 4 events each
    for eid in ("OB_EV41738025", "OB_EV41744631", "OB_EV41770054"):
        assert api.event_url(eid) not in fetched  # Europe / US / virtual


def test_us_region_fetches_us_canada(
        tmp_path, williamhill_day_index_payload, williamhill_racecard_3pl):
    s = _StubSession(williamhill_day_index_payload,
                     {"OB_EV41744631": williamhill_racecard_3pl})
    rc, out = _run(s, tmp_path, ["us"])
    assert rc == 0
    assert json.loads(out.read_text())["races"][0]["country"] == "us-canada"


def test_empty_day_writes_empty_output_and_exits_0(tmp_path):
    rc, out = _run(_StubSession({"regionCompetitions": []}, {}), tmp_path)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 0 and data["races"] == []


def test_all_races_failing_exits_1(tmp_path, williamhill_day_index_payload):
    rc, _ = _run(_StubSession(williamhill_day_index_payload, {}), tmp_path)
    assert rc == 1


def test_races_already_off_are_not_fetched(
        tmp_path, williamhill_day_index_payload, williamhill_racecard_3pl):
    s = _StubSession(williamhill_day_index_payload,
                     {"OB_EV41748428": williamhill_racecard_3pl})
    late = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
    cli.main(["gb-ie"], now_utc=late, make_session=lambda: s,
             out_path=tmp_path / "williamhill.json")
    fetched = set(s.fetched) - {api.DAY_INDEX_URL}
    # Only Warwick 14:03 and Sedgefield 14:29 are still to run.
    assert fetched == {api.event_url("OB_EV41748428"), api.event_url("OB_EV41748418")}
