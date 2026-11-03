"""Dataclasses mirroring williamhill.json. snake_case here; the
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
class WilliamHillRunner:
    name: str
    win_price: float | None
    win_price_raw: str | None

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "WilliamHillRunner":
        return cls(
            name=d["name"],
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )


@dataclass(frozen=True)
class WilliamHillRace:
    venue: str
    country: str  # William Hill's region-filter id, e.g. "uk-ireland"
    off_time: str
    market_name: str
    scraped_at: str
    each_way_terms: EachWayTerms | None
    runners: list[WilliamHillRunner] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "WilliamHillRace":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            scraped_at=d["scrapedAt"],
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[WilliamHillRunner.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class WilliamHillOutput:
    scraped_at: str
    race_count: int
    races: list[WilliamHillRace] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "WilliamHillOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[WilliamHillRace.from_dict(r) for r in d.get("races", [])],
        )


@dataclass(frozen=True)
class WilliamHillStub:
    """Internal: metadata-only race entry from the day index.
    Not emitted in williamhill.json."""
    event_id: str
    venue: str
    country: str
    start_time_utc: str
