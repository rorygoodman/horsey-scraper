"""Region parsing and London-day windowing. Pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us": frozenset({"US"}),
}

_VALID_IDS_MSG = "valid: " + ",".join(sorted(REGION_COUNTRIES.keys()))


def parse_regions(arg: str) -> frozenset[str]:
    """Parse a comma-separated region string into a union of ISO country codes.

    Raises ValueError on empty input or any unknown region id."""
    stripped = arg.strip()
    if not stripped:
        raise ValueError(f"regions must be non-empty; {_VALID_IDS_MSG}")
    ids = [part.strip() for part in stripped.split(",")]
    unknown = [i for i in ids if i not in REGION_COUNTRIES]
    if unknown:
        raise ValueError(
            f"regions must be non-empty; {_VALID_IDS_MSG}, got: '{unknown[0]}'"
        )
    out: set[str] = set()
    for i in ids:
        out |= REGION_COUNTRIES[i]
    return frozenset(out)


def london_day_window(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return (now_utc, end_of_today_london_in_utc).

    `end` is midnight of *tomorrow* in Europe/London, converted back to UTC
    (exclusive upper bound). A race at 23:59 London passes; 00:00 next-day
    London does not."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    now_london = now_utc.astimezone(LONDON)
    tomorrow_london = (now_london + timedelta(days=1)).date()
    end_london = datetime.combine(tomorrow_london, time(0, 0), tzinfo=LONDON)
    end_utc = end_london.astimezone(timezone.utc)
    return (now_utc, end_utc)


def in_window(
    start_time_utc: str, window: tuple[datetime, datetime]
) -> bool:
    """`start_time_utc` is an ISO-8601 UTC string ('Z' or +00:00 form).
    Returns True iff window[0] <= parsed < window[1]."""
    # PaddyPower's startTime is '2026-05-26T17:39:00.000Z'. Python 3.11 fromisoformat
    # accepts 'Z' as a UTC suffix.
    parsed = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return window[0] <= parsed < window[1]
