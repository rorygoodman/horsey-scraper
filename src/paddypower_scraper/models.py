"""Dataclasses mirroring paddypower.json. snake_case here; the
snake→camel conversion happens in output.py."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EachWayTerms:
    fraction: float
    places: int


@dataclass(frozen=True)
class PaddyRunner:
    name: str
    selection_id: int | None
    win_price: float | None
    win_price_raw: str | None


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


@dataclass(frozen=True)
class PaddyOutput:
    scraped_at: str
    race_count: int
    races: list[PaddyRace] = field(default_factory=list)


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
