"""Parse the content-managed-page/v7?cardsToFetch=63 response.

This endpoint returns every race PaddyPower lists (spanning ~3 days,
all countries) with metadata only — no prices, no runners. Used as
the meetings index that drives per-meeting fan-out."""

from __future__ import annotations

from .models import RaceStub


def parse_meetings_index(payload: dict) -> list[RaceStub]:
    """Walk payload['attachments']['races'], emit one RaceStub per
    race that has all required metadata fields.

    Silently drops races missing any of: raceId, meetingId, winMarketId,
    startTime, countryCode, venue. Empty/missing attachments → []."""
    races = (
        payload.get("attachments", {})
        if isinstance(payload, dict) else {}
    ).get("races", {})
    if not isinstance(races, dict):
        return []
    out: list[RaceStub] = []
    for entry in races.values():
        if not isinstance(entry, dict):
            continue
        try:
            stub = RaceStub(
                race_id=entry["raceId"],
                meeting_id=entry["meetingId"],
                win_market_id=entry["winMarketId"],
                start_time_utc=entry["startTime"],
                country_code=entry["countryCode"],
                venue=entry["venue"],
            )
        except (KeyError, TypeError):
            continue
        # Defensive: drop entries whose required fields are missing,
        # empty, or not strings (RaceStub fields are all str).
        if not all(isinstance(v, str) and v for v in (
                stub.race_id, stub.meeting_id, stub.win_market_id,
                stub.start_time_utc, stub.country_code, stub.venue)):
            continue
        out.append(stub)
    return out
