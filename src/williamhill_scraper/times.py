"""Normalize William Hill timestamps. Pure, no I/O.

The API writes instants as '2026-11-03T15:48:00.000+0000': millis plus a
colon-less offset. Converted here once so nothing downstream has to know."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from common.timeutil import iso_utc

_COLONLESS_OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")


def to_iso_utc(raw: object) -> "str | None":
    """'...+0000' → '...Z' UTC instant string; None if unparseable."""
    if not (isinstance(raw, str) and raw):
        return None
    s = _COLONLESS_OFFSET.sub(r"\1:\2", raw.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return iso_utc(parsed.replace(microsecond=0))
