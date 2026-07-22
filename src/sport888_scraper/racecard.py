"""Parse a getRacecard response into one Sport888Race.

Winner-market runners are `selections_details` entries with market_id == "1".
Each-way terms come from `each_way_terms[<eventId>]` when allow_each_way == "1"
(fraction = 1 / place_odds_divisor, places = places_paid)."""

from __future__ import annotations

from .models import EachWayTerms, Sport888Race, Sport888Runner

WINNER_MARKET_ID = "1"


def parse_racecard(payload: dict, scraped_at_utc: str) -> "Sport888Race | None":
    rc = payload.get("racecard") if isinstance(payload, dict) else None
    if not isinstance(rc, dict):
        return None
    events = rc.get("events")
    if not isinstance(events, dict) or not events:
        return None
    event_id, event = next(iter(events.items()))
    details = event.get("details") if isinstance(event, dict) else None
    if not isinstance(details, dict):
        return None
    venue = details.get("name")
    start = details.get("scheduled_start")
    if not (isinstance(venue, str) and venue and isinstance(start, str) and start):
        return None
    runners = _parse_runners(rc.get("selections_details"))
    if not runners:
        return None
    return Sport888Race(
        venue=venue,
        country=details.get("category_slug") or "",
        off_time=start,  # already an ISO offset string, e.g. "...+00:00"
        market_name="Winner Market",
        scraped_at=scraped_at_utc,
        each_way_terms=_parse_eachway(rc.get("each_way_terms"), str(event_id)),
        runners=runners,
    )


def _parse_eachway(terms: object, event_id: str) -> "EachWayTerms | None":
    if not isinstance(terms, dict):
        return None
    t = terms.get(event_id)
    if not isinstance(t, dict) or t.get("allow_each_way") != "1":
        return None
    try:
        divisor = int(t["place_odds_divisor"])
        places = int(t["places_paid"])
    except (KeyError, TypeError, ValueError):
        return None
    if divisor <= 0 or places <= 0:
        return None
    fraction = 1.0 / divisor
    if not (0.0 < fraction <= 1.0):
        return None
    return EachWayTerms(fraction=fraction, places=places)


def _parse_runners(sels: object) -> list[Sport888Runner]:
    if not isinstance(sels, dict):
        return []
    out: list[Sport888Runner] = []
    for s in sels.values():
        if not isinstance(s, dict) or s.get("market_id") != WINNER_MARKET_ID:
            continue
        name = s.get("name")
        if not isinstance(name, str) or not name:
            continue
        price = _to_float(s.get("decimal_price"))
        raw = s.get("fraction_price")
        raw = raw if isinstance(raw, str) and raw else None
        active = s.get("active") == "1"
        betable = s.get("betable") is True
        if not (active and betable) or price is None or price <= 0.0 or raw is None:
            price = None
            raw = None
        out.append(Sport888Runner(name=name, win_price=price, win_price_raw=raw))
    return out


def _to_float(v: object) -> "float | None":
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
