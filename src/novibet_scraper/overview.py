"""Parse the horse-racing-overview2 day index into race stubs.

The payload nests days → countries → meetings → races. Venue lives on the
meeting, the country caption on the country, and the id/off-time on the
race. Day and region filtering are the CLI's job, so this returns every
well-formed stub from every day in the payload."""

from __future__ import annotations

from .models import NovibetStub


def parse_overview(payload: dict) -> list[NovibetStub]:
    """One NovibetStub per race entry that has both a betContextId and a
    startTimeUTC, plus a venue and country caption. Drops anything else."""
    days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(days, list):
        return []
    out: list[NovibetStub] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        for country in day.get("countries") or []:
            if not isinstance(country, dict):
                continue
            country_caption = country.get("caption")
            if not (isinstance(country_caption, str) and country_caption):
                continue
            for meeting in country.get("meetings") or []:
                if not isinstance(meeting, dict):
                    continue
                venue = meeting.get("caption")
                if not (isinstance(venue, str) and venue):
                    continue
                for race in meeting.get("races") or []:
                    if not isinstance(race, dict):
                        continue
                    bcid = race.get("betContextId")
                    bcid = (str(bcid)
                            if isinstance(bcid, (str, int)) and str(bcid)
                            else None)
                    start = race.get("startTimeUTC")
                    if not (bcid and isinstance(start, str) and start):
                        continue
                    out.append(NovibetStub(
                        bet_context_id=bcid,
                        venue=venue,
                        country=country_caption,
                        start_time_utc=start,
                    ))
    return out
