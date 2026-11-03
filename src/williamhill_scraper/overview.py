"""Parse the region-competitions day index into race stubs.

The payload nests regionCompetitions → competitions → events. The region
filter id lives on the region, the venue on the competition, and the event
id/off-time on the event. Day and region filtering are the CLI's job, so
this returns every well-formed stub in the payload."""

from __future__ import annotations

from .models import WilliamHillStub
from .times import to_iso_utc


def parse_day_index(payload: dict) -> list[WilliamHillStub]:
    """One WilliamHillStub per event that has an id and a parseable
    startDateTime, under a named competition and region. Settled events and
    abandoned meetings are dropped; anything malformed is skipped."""
    regions = payload.get("regionCompetitions") if isinstance(payload, dict) else None
    if not isinstance(regions, list):
        return []
    out: list[WilliamHillStub] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        rf = region.get("regionFilter")
        region_id = rf.get("id") if isinstance(rf, dict) else None
        if not (isinstance(region_id, str) and region_id):
            continue
        for comp in region.get("competitions") or []:
            if not isinstance(comp, dict):
                continue
            meta = comp.get("competition")
            if not isinstance(meta, dict) or meta.get("_abandoned") is True:
                continue
            venue = meta.get("name")
            if not (isinstance(venue, str) and venue):
                continue
            for event in comp.get("events") or []:
                if not isinstance(event, dict) or event.get("settled") is True:
                    continue
                eid = event.get("id")
                start = to_iso_utc(event.get("startDateTime"))
                if not (isinstance(eid, str) and eid and start):
                    continue
                out.append(WilliamHillStub(
                    event_id=eid,
                    venue=venue,
                    country=region_id,
                    start_time_utc=start,
                ))
    return out
