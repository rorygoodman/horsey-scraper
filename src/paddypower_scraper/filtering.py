"""London-day windowing and in-window check for already-fetched races.
Region parsing now lives in common.regions; re-exported for convenience."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from common.regions import REGION_COUNTRIES, countries_for_all, parse_regions

__all__ = [
    "REGION_COUNTRIES",
    "countries_for_all",
    "parse_regions",
    "london_day_window",
    "in_window",
    "LONDON",
]

LONDON = ZoneInfo("Europe/London")


def london_day_window(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return (now_utc, end_of_today_london_in_utc).

    `end` is midnight of *tomorrow* Europe/London converted to UTC
    (exclusive). A race at 23:59 London passes; 00:00 next-day does not."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    now_london = now_utc.astimezone(LONDON)
    tomorrow_london = (now_london + timedelta(days=1)).date()
    end_london = datetime.combine(tomorrow_london, time(0, 0), tzinfo=LONDON)
    return (now_utc, end_london.astimezone(timezone.utc))


def in_window(start_time_utc: str, window: tuple[datetime, datetime]) -> bool:
    """`start_time_utc` is an ISO-8601 UTC string. True iff
    window[0] <= parsed < window[1]."""
    parsed = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return window[0] <= parsed < window[1]
