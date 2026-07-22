"""Tests for the arb_finder CLI --source 888 mode (writes 888horses.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arb_finder import cli
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from betfair_scraper.models import write_betfair_json
from common.markettype import MarketType
from sport888_scraper.models import (
    EachWayTerms, Sport888Output, Sport888Race, Sport888Runner,
)
from sport888_scraper.output import write_sport888_json

NOW = datetime(2026, 7, 22, 12, 1, tzinfo=timezone.utc)


def _write_inputs(tmp_path: Path):
    bf = ScrapeOutput(
        "2026-07-22T12:00:00Z", 1,
        [RaceOdds("1.1", "Worcester", "GB", "2026-07-22T13:55:00+01:00", "u",
                  "12:55 Worcester",
                  {MarketType.WIN: "2026-07-22T12:00:00Z",
                   MarketType.TOP_3: "2026-07-22T12:00:00Z"},
                  [RunnerOdds("Holy Legend",
                              {MarketType.WIN: 2.0, MarketType.TOP_3: 1.4}, 99)])])
    e = Sport888Output(
        "2026-07-22T12:00:30Z", 1,
        [Sport888Race("Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00",
                      "Winner Market", "2026-07-22T12:00:30Z", EachWayTerms(0.2, 3),
                      [Sport888Runner("Holy Legend", 3.0, "2/1")])])
    write_betfair_json(bf, tmp_path / "betfair.json")
    write_sport888_json(e, tmp_path / "888sport.json")


def test_source_888_writes_888horses(tmp_path: Path):
    _write_inputs(tmp_path)
    rc = cli.main(
        ["--source", "888",
         str(tmp_path / "betfair.json"),
         str(tmp_path / "888sport.json"),
         str(tmp_path / "888horses.json")],
        now=lambda: NOW)
    assert rc == 0
    data = json.loads((tmp_path / "888horses.json").read_text())
    assert data["horseCount"] == 1
    assert data["horses"][0]["sport888"]["winPrice"] == 3.0
    assert data["horses"][0]["betfairWinMarketId"] == "1.1"


def test_source_888_missing_input_exits_2(tmp_path: Path):
    rc = cli.main(
        ["--source", "888",
         str(tmp_path / "nope.json"),
         str(tmp_path / "also-nope.json"),
         str(tmp_path / "out.json")],
        now=lambda: NOW)
    assert rc == 2


def test_unknown_source_exits_1(tmp_path: Path):
    rc = cli.main(["--source", "ladbrokes"], now=lambda: NOW)
    assert rc == 1


def test_default_source_still_paddypower(tmp_path: Path, monkeypatch):
    # No --source, no args → existing paddypower path. Missing default inputs
    # → input error (exit 2), proving the default branch is taken unchanged.
    monkeypatch.chdir(tmp_path)
    rc = cli.main([], now=lambda: NOW)
    assert rc == 2
