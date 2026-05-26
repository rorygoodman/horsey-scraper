"""Time helpers: UTC→Europe/London ISO-offset strings, and UTC-instant
formatting. Pure, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def utc_to_london(iso_utc_str: str) -> "str | None":
    """Convert an ISO-8601 UTC string to a Europe/London ISO-offset string.

    Returns None on unparseable input. A UTC instant renders with a 'Z'
    suffix when London is on GMT (+00:00) and '+01:00' when on BST,
    matching the Kotlin ISO_OFFSET_DATE_TIME output."""
    try:
        parsed = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    london = parsed.astimezone(LONDON)
    return london.isoformat().replace("+00:00", "Z")


def iso_utc(dt: datetime) -> str:
    """Format an aware datetime as an ISO-8601 UTC instant ('...Z')."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
