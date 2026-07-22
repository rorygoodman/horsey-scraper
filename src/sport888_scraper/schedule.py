"""Parse the getSchedule?tab=today response into race stubs.

The response groups the whole day category → meeting → event ids, but every
event's flat metadata lives under `event_details[<eventId>]`. We read that map
directly (venue name, scheduled_start, category_slug) — region filtering is the
CLI's job, so this returns every well-formed stub regardless of region."""

from __future__ import annotations

from .models import Sport888Stub


def parse_schedule(payload: dict) -> list[Sport888Stub]:
    """One Sport888Stub per event_details entry that has all of: id, name
    (venue), category_slug, scheduled_start. Drops anything incomplete."""
    event_details = payload.get("event_details") if isinstance(payload, dict) else None
    if not isinstance(event_details, dict):
        return []
    out: list[Sport888Stub] = []
    for entry in event_details.values():
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        eid = str(eid) if isinstance(eid, (str, int)) and str(eid) else None
        venue = entry.get("name")
        slug = entry.get("category_slug")
        start = entry.get("scheduled_start")
        if not (eid and isinstance(venue, str) and venue
                and isinstance(slug, str) and slug
                and isinstance(start, str) and start):
            continue
        out.append(Sport888Stub(
            event_id=eid, venue=venue, category_slug=slug, start_time_utc=start,
        ))
    return out
