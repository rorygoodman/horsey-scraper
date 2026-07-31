"""Dataclasses mirroring the priced-arb output files + serializer.

One set of models serves every bookie. The only per-bookie variation is
JSON key naming, which comes from bookies.Bookie via build_rename()."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.jsonio import write_json
from common.markettype import MarketType

from .bookies import Bookie


class EachWayTermsLike(Protocol):
    """Any scraper's EachWayTerms. Structural on purpose: each scraper
    package owns its own dataclass, and jsonio serializes it by shape."""
    fraction: float
    places: int


@dataclass(frozen=True)
class BookiePriceLeg:
    win_price: float
    win_price_raw: str
    each_way_terms: EachWayTermsLike


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
class PricedHorse:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: Runner
    bookie: BookiePriceLeg
    betfair: BetfairLayLeg
    edge: float


@dataclass(frozen=True)
class BookieHorsesOutput:
    computed_at: str
    betfair_scraped_at: str
    bookie_scraped_at: str
    horse_count: int
    horses: list[PricedHorse]


_BASE_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
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


def build_rename(bookie: Bookie) -> dict[str, str]:
    """Shared snake→camel map plus the two bookie-specific names."""
    return {
        **_BASE_RENAME,
        "bookie_scraped_at": bookie.scraped_at_field,
        "bookie": bookie.leg_field,
    }


def write_bookie_horses_json(
    out: BookieHorsesOutput, bookie: Bookie, path: Path | str
) -> None:
    write_json(out, build_rename(bookie), path)
