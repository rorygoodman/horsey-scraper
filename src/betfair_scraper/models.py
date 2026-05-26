"""Dataclasses mirroring betfair.json + serialize/deserialize.

snake_case fields; the snake→camel rename happens at the JSON boundary
via common.jsonio. MarketType enum keys/values serialize as their .name."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.jsonio import write_json
from common.markettype import MarketType

# ---- internal (not serialized) intermediate types ----


@dataclass(frozen=True)
class Race:
    race_id: str
    venue: str
    country: str
    off_time: str
    win_market_url: str


@dataclass(frozen=True)
class RunnerEntry:
    selection_id: int | None
    name: str
    lay: float | None


@dataclass(frozen=True)
class MarketScrape:
    type: MarketType
    scraped_at: str
    runners: list[RunnerEntry]


# ---- serialized output types ----


@dataclass(frozen=True)
class RunnerOdds:
    name: str
    lay: dict[MarketType, float | None]
    selection_id: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunnerOdds":
        return cls(
            name=d["name"],
            lay={MarketType[k]: v for k, v in d["lay"].items()},
            selection_id=d.get("selectionId"),
        )


@dataclass(frozen=True)
class RaceOdds:
    race_id: str
    venue: str
    country: str
    off_time: str
    win_market_url: str
    market_name: str
    market_scraped_at: dict[MarketType, str]
    runners: list[RunnerOdds]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RaceOdds":
        return cls(
            race_id=d["raceId"],
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            win_market_url=d["winMarketUrl"],
            market_name=d["marketName"],
            market_scraped_at={
                MarketType[k]: v for k, v in d["marketScrapedAt"].items()
            },
            runners=[RunnerOdds.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class ScrapeOutput:
    scraped_at: str
    race_count: int
    races: list[RaceOdds]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScrapeOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[RaceOdds.from_dict(r) for r in d.get("races", [])],
        )


BETFAIR_RENAME = {
    "race_id": "raceId",
    "off_time": "offTime",
    "win_market_url": "winMarketUrl",
    "market_name": "marketName",
    "market_scraped_at": "marketScrapedAt",
    "selection_id": "selectionId",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_betfair_json(out: ScrapeOutput, path: Path | str) -> None:
    write_json(out, BETFAIR_RENAME, path)
