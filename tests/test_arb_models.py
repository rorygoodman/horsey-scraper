"""Tests for arb_finder.models serialization."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    Arb,
    ArbOutput,
    ArbRunner,
    BetfairLayLeg,
    PaddyPriceLeg,
    write_arbs_json,
)


def _sample() -> ArbOutput:
    return ArbOutput(
        computed_at="2026-05-25T17:06:08.398333Z",
        betfair_scraped_at="2026-05-25T17:05:56.890289Z",
        paddypower_scraped_at="2026-05-25T17:05:58.384555Z",
        arb_count=1,
        arbs=[
            Arb(
                venue="Ballinrobe",
                country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                market_name="18:05 Ballinrobe",
                betfair_win_market_id="1.258528220",
                runner=ArbRunner(name="Sony Bill", selection_id=66986352),
                paddypower=PaddyPriceLeg(
                    win_price=3.0, win_price_raw="2/1",
                    each_way_terms=EachWayTerms(fraction=0.2, places=2)),
                betfair=BetfairLayLeg(
                    win_lay=2.0, top_n_lay=1.4, top_n_type=MarketType.TOP_2),
                margin=0.25,
            )
        ],
    )


def test_serialize_shape(tmp_path: Path):
    target = tmp_path / "arbs.json"
    write_arbs_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert list(payload.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "arbCount", "arbs",
    ]
    arb = payload["arbs"][0]
    assert list(arb.keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "margin",
    ]
    assert arb["runner"] == {"name": "Sony Bill", "selectionId": 66986352}
    assert arb["paddypower"] == {
        "winPrice": 3.0, "winPriceRaw": "2/1",
        "eachWayTerms": {"fraction": 0.2, "places": 2}}
    assert arb["betfair"] == {"winLay": 2.0, "topNLay": 1.4, "topNType": "TOP_2"}


def test_empty_arbs(tmp_path: Path):
    out = ArbOutput("2026-05-25T17:06:08.398333Z", "2026-05-25T17:05:56.890289Z",
                    "2026-05-25T17:05:58.384555Z", 0, [])
    target = tmp_path / "arbs.json"
    write_arbs_json(out, target)
    assert json.loads(target.read_text())["arbs"] == []
