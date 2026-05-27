"""Tests for arb_finder.models (horses.json) serialization."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    BetfairLayLeg,
    Horse,
    HorsesOutput,
    PaddyPriceLeg,
    Runner,
    write_horses_json,
)


def _sample() -> HorsesOutput:
    return HorsesOutput(
        computed_at="2026-05-27T20:34:11Z",
        betfair_scraped_at="2026-05-27T20:34:01Z",
        paddypower_scraped_at="2026-05-27T20:34:05Z",
        horse_count=1,
        horses=[
            Horse(
                venue="Finger Lakes",
                country="US",
                off_time="2026-05-27T21:47:00+01:00",
                market_name="21:47 Finger Lakes",
                betfair_win_market_id="1.258619108",
                runner=Runner(name="Emerald Forest", selection_id=12345678),
                paddypower=PaddyPriceLeg(
                    win_price=2.88, win_price_raw="15/8",
                    each_way_terms=EachWayTerms(fraction=0.25, places=2)),
                betfair=BetfairLayLeg(
                    win_lay=2.92, place_lay=1.64, place_market=MarketType.TOP_2),
                edge=-0.0599,
            )
        ],
    )


def test_serialize_shape(tmp_path: Path):
    target = tmp_path / "horses.json"
    write_horses_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert list(payload.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "horseCount", "horses",
    ]
    h = payload["horses"][0]
    assert list(h.keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "edge",
    ]
    assert h["runner"] == {"name": "Emerald Forest", "selectionId": 12345678}
    assert h["paddypower"] == {
        "winPrice": 2.88, "winPriceRaw": "15/8",
        "eachWayTerms": {"fraction": 0.25, "places": 2}}
    assert h["betfair"] == {"winLay": 2.92, "placeLay": 1.64, "placeMarket": "TOP_2"}
    assert h["edge"] == -0.0599  # negative edge is kept


def test_empty_horses(tmp_path: Path):
    out = HorsesOutput("2026-05-27T20:34:11Z", "2026-05-27T20:34:01Z",
                       "2026-05-27T20:34:05Z", 0, [])
    target = tmp_path / "horses.json"
    write_horses_json(out, target)
    assert json.loads(target.read_text())["horses"] == []
