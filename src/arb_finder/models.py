"""Dataclasses mirroring arbs.json + serializer. Port of ArbModels.kt."""

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
    top_n_lay: float
    top_n_type: MarketType


@dataclass(frozen=True)
class ArbRunner:
    name: str
    selection_id: int


@dataclass(frozen=True)
class Arb:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: ArbRunner
    paddypower: PaddyPriceLeg
    betfair: BetfairLayLeg
    margin: float


@dataclass(frozen=True)
class ArbOutput:
    computed_at: str
    betfair_scraped_at: str
    paddypower_scraped_at: str
    arb_count: int
    arbs: list[Arb]


ARB_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
    "paddypower_scraped_at": "paddypowerScrapedAt",
    "arb_count": "arbCount",
    "off_time": "offTime",
    "market_name": "marketName",
    "betfair_win_market_id": "betfairWinMarketId",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "each_way_terms": "eachWayTerms",
    "win_lay": "winLay",
    "top_n_lay": "topNLay",
    "top_n_type": "topNType",
}


def write_arbs_json(out: ArbOutput, path: Path | str) -> None:
    write_json(out, ARB_RENAME, path)
