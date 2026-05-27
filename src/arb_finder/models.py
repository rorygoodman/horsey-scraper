"""Dataclasses mirroring horses.json + serializer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.jsonio import write_json
from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms


@dataclass(frozen=True)
class PaddyPriceLeg:
    win_price: float
    win_price_raw: str
    each_way_terms: EachWayTerms


@dataclass(frozen=True)
class BetfairLayLeg:
    win_lay: float
    place_lay: float
    place_market: MarketType


@dataclass(frozen=True)
class Runner:
    name: str
    selection_id: int


@dataclass(frozen=True)
class Horse:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: Runner
    paddypower: PaddyPriceLeg
    betfair: BetfairLayLeg
    edge: float


@dataclass(frozen=True)
class HorsesOutput:
    computed_at: str
    betfair_scraped_at: str
    paddypower_scraped_at: str
    horse_count: int
    horses: list[Horse]


HORSES_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
    "paddypower_scraped_at": "paddypowerScrapedAt",
    "horse_count": "horseCount",
    "off_time": "offTime",
    "market_name": "marketName",
    "betfair_win_market_id": "betfairWinMarketId",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "each_way_terms": "eachWayTerms",
    "win_lay": "winLay",
    "place_lay": "placeLay",
    "place_market": "placeMarket",
}


def write_horses_json(out: HorsesOutput, path: Path | str) -> None:
    write_json(out, HORSES_RENAME, path)
