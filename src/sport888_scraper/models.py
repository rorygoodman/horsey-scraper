"""Dataclasses mirroring 888sport.json. snake_case here; the
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
class Sport888Runner:
    name: str
    win_price: float | None
    win_price_raw: str | None

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Runner":
        return cls(
            name=d["name"],
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )


@dataclass(frozen=True)
class Sport888Race:
    venue: str
    country: str  # 888 category slug, e.g. "uk-and-ireland"
    off_time: str
    market_name: str
    scraped_at: str
    each_way_terms: EachWayTerms | None
    runners: list[Sport888Runner] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Race":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            scraped_at=d["scrapedAt"],
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[Sport888Runner.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class Sport888Output:
    scraped_at: str
    race_count: int
    races: list[Sport888Race] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Output":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[Sport888Race.from_dict(r) for r in d.get("races", [])],
        )


@dataclass(frozen=True)
class Sport888Stub:
    """Internal: metadata-only race entry from the schedule index.
    Not emitted in 888sport.json."""
    event_id: str
    venue: str
    category_slug: str
    start_time_utc: str
