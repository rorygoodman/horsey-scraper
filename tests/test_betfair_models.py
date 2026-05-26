"""Tests for betfair_scraper.models: dataclasses, serialize, deserialize."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from betfair_scraper.models import (
    RaceOdds,
    RunnerOdds,
    ScrapeOutput,
    write_betfair_json,
)


def _sample() -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-05-25T17:05:56.890289Z",
        race_count=1,
        races=[
            RaceOdds(
                race_id="1.258528220",
                venue="Ballinrobe",
                country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                win_market_url="https://www.betfair.com/exchange/plus/horse-racing/market/1.258528220",
                market_name="18:05 Ballinrobe - 2m1f Beg Chs",
                market_scraped_at={
                    MarketType.WIN: "2026-05-25T17:05:58.303431Z",
                    MarketType.TOP_2: "2026-05-25T17:05:58.303431Z",
                },
                runners=[
                    RunnerOdds(
                        name="Sony Bill",
                        lay={MarketType.WIN: 2.72, MarketType.TOP_2: 1.99},
                        selection_id=66986352,
                    ),
                    RunnerOdds(
                        name="No Price",
                        lay={MarketType.WIN: None, MarketType.TOP_2: None},
                        selection_id=None,
                    ),
                ],
            )
        ],
    )


def test_serialize_shape_and_key_order(tmp_path: Path):
    target = tmp_path / "betfair.json"
    write_betfair_json(_sample(), target)
    raw = target.read_text()
    payload = json.loads(raw)

    assert list(payload.keys()) == ["scrapedAt", "raceCount", "races"]
    race = payload["races"][0]
    assert list(race.keys()) == [
        "raceId", "venue", "country", "offTime",
        "winMarketUrl", "marketName", "marketScrapedAt", "runners",
    ]
    assert list(race["runners"][0].keys()) == ["name", "lay", "selectionId"]
    assert race["marketScrapedAt"]["WIN"] == "2026-05-25T17:05:58.303431Z"
    assert race["runners"][0]["lay"] == {"WIN": 2.72, "TOP_2": 1.99}
    assert race["runners"][1]["lay"] == {"WIN": None, "TOP_2": None}
    assert race["runners"][1]["selectionId"] is None


def test_selection_id_stays_int(tmp_path: Path):
    target = tmp_path / "betfair.json"
    write_betfair_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert isinstance(payload["races"][0]["runners"][0]["selectionId"], int)


def test_round_trip_from_dict():
    out = _sample()
    import tempfile, os
    fd, name = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_betfair_json(out, name)
    reloaded = ScrapeOutput.from_dict(json.loads(Path(name).read_text()))
    os.unlink(name)
    assert reloaded == out
