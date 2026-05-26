"""Dataclasses mirroring paddypower.json. snake_case here; the
snake→camel conversion happens in output.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EachWayTerms:
    fraction: float
    places: int

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "EachWayTerms":
        return cls(fraction=d["fraction"], places=d["places"])


@dataclass(frozen=True)
class PaddyRunner:
    name: str
    selection_id: int | None
    win_price: float | None
    win_price_raw: str | None

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyRunner":
        return cls(
            name=d["name"],
            selection_id=d.get("selectionId"),
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )


@dataclass(frozen=True)
class PaddyRace:
    venue: str
    country: str
    off_time: str
    market_name: str
    race_url: str
    scraped_at: str
    betfair_win_market_id: str | None
    each_way_terms: EachWayTerms | None
    runners: list[PaddyRunner] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyRace":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            race_url=d["raceUrl"],
            scraped_at=d["scrapedAt"],
            betfair_win_market_id=d.get("betfairWinMarketId"),
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[PaddyRunner.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class PaddyOutput:
    scraped_at: str
    race_count: int
    races: list[PaddyRace] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[PaddyRace.from_dict(r) for r in d.get("races", [])],
        )


@dataclass(frozen=True)
class RaceStub:
    """Internal: metadata-only race entry from the meetings index.
    Not emitted in paddypower.json."""
    race_id: str
    meeting_id: str
    win_market_id: str
    start_time_utc: str
    country_code: str
    venue: str
