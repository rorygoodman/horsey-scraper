"""Tests for the Betfair CLI orchestration (injected fake client)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from betfair_scraper.cli import main


class FakeClient:
    def __init__(self):
        self.logged_in = False

    def login(self, u, p):
        self.logged_in = True

    def list_market_catalogue(self, body: str) -> str:
        codes = json.loads(body)["filter"]["marketTypeCodes"]
        if codes == ["WIN"]:
            return json.dumps([{
                "marketId": "1.1", "marketName": "2m Hcap",
                "marketStartTime": "2026-05-25T17:00:00Z",
                "event": {"id": "30.1", "venue": "Ascot", "countryCode": "GB"},
                "runners": [{"selectionId": 1, "runnerName": "A"}],
            }])
        return json.dumps([])

    def list_market_book(self, body: str) -> str:
        return json.dumps([{
            "marketId": "1.1", "status": "OPEN",
            "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}],
        }])


def cli_creds():
    from betfair_scraper.credentials import Credentials
    return Credentials("u", "p", "k")


def test_happy_path_writes_betfair_json(tmp_path: Path, monkeypatch, capsys):
    import betfair_scraper.cli as cli
    monkeypatch.setattr(cli, "load_credentials", lambda _p: cli_creds())
    out = tmp_path / "betfair.json"
    rc = main(
        ["gb-ie"],
        make_client=lambda app_key: FakeClient(),
        now=lambda: datetime(2026, 5, 25, 17, 0, tzinfo=timezone.utc),
        out_path=out,
    )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["raceCount"] == 1
    assert payload["races"][0]["raceId"] == "1.1"
    assert "regions=gb-ie" in capsys.readouterr().out


def test_bad_region_exits_1(monkeypatch):
    import betfair_scraper.cli as cli
    monkeypatch.setattr(cli, "load_credentials", lambda _p: cli_creds())
    assert main(["xx"], make_client=lambda app_key: FakeClient()) == 1
