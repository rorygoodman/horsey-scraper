"""ISO-8601 validation helpers shared by the schema validators.

`is_iso_utc`  — the 'Z' UTC-instant form (java.time.Instant.parse equiv).
`is_iso_offset_datetime` — any date-time carrying an explicit offset
                           (ISO_OFFSET_DATE_TIME equiv), 'Z' or +hh:mm."""

from __future__ import annotations

from datetime import datetime


def is_iso_utc(v: str) -> bool:
    """True iff `v` is an ISO-8601 instant in the trailing-'Z' UTC form."""
    if not v.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def is_iso_offset_datetime(v: str) -> bool:
    """True iff `v` is an ISO-8601 date-time with an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() is not None
