"""Parse the racing-page/v7 response into PaddyRace objects.

This endpoint returns the whole meeting (every race) plus every market
for those races at TOP LEVEL (not under 'attachments' like the
content-managed-page response — that's the gotcha that justifies a
separate parser module)."""

from __future__ import annotations

import sys

from common.timeutil import utc_to_london as _utc_to_london

from .models import EachWayTerms, PaddyRace, PaddyRunner

SYNTHETIC_RUNNER_NAMES = frozenset({
    "Unnamed Favourite",
    "Unnamed 2nd Favourite",
    "The Field",
})


def parse_meeting_response(
    payload: dict, scraped_at_utc: str
) -> list[PaddyRace]:
    """Iterate payload['races'] and build PaddyRace records.

    Skips entries where winMarketId is null (exchange-history rows) or
    the WIN market is missing from payload['markets']. Drops races with
    no usable runners. Logs (stderr) when dropping a race for missing
    country code."""
    races = payload.get("races", {})
    markets = payload.get("markets", {})
    if not isinstance(races, dict) or not isinstance(markets, dict):
        return []

    out: list[PaddyRace] = []
    for race in races.values():
        if not isinstance(race, dict):
            continue
        win_market_id = race.get("winMarketId")
        if not win_market_id:
            continue  # exchange-history row
        market = markets.get(win_market_id)
        if not isinstance(market, dict):
            continue  # market missing — skip silently
        venue = race.get("venue") or ""
        country = race.get("countryCode")
        if not country:
            print(
                f"paddy: dropping race {race.get('raceId')} venue={venue}: "
                "no countryCode",
                file=sys.stderr,
            )
            continue
        start_time_utc = race.get("startTime")
        if not start_time_utc:
            continue
        off_time = _utc_to_london(start_time_utc)
        if off_time is None:
            continue
        runners = _parse_runners(market)
        if not runners:
            continue
        ew = _parse_eachway(market)
        race_type = race.get("winMarketName") or market.get("marketName") or ""
        out.append(PaddyRace(
            venue=venue,
            country=country,
            off_time=off_time,
            market_name=_market_name(off_time, venue, race_type),
            race_url="",  # racing-page response doesn't expose a stable per-race URL
            scraped_at=scraped_at_utc,
            betfair_win_market_id=market.get("exchangeMarketId"),
            each_way_terms=ew,
            runners=runners,
        ))
    return out


def _parse_runners(market: dict) -> list[PaddyRunner]:
    raw = market.get("runners", [])
    if not isinstance(raw, list):
        return []
    out: list[PaddyRunner] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        name = r.get("runnerName")
        if not isinstance(name, str) or not name:
            continue
        if name in SYNTHETIC_RUNNER_NAMES:
            continue
        selection_id = r.get("selectionId")
        if not isinstance(selection_id, int):
            selection_id = None
        status = r.get("runnerStatus") or "ACTIVE"
        odds = r.get("winRunnerOdds")
        odds = odds.get("trueOdds") if isinstance(odds, dict) else None
        is_active_with_odds = status == "ACTIVE" and isinstance(odds, dict) and odds
        decimal_val = None
        fractional_val = None
        if is_active_with_odds:
            d = odds.get("decimalOdds")
            if isinstance(d, dict):
                v = d.get("decimalOdds")
                if isinstance(v, (int, float)):
                    decimal_val = float(v)
            f = odds.get("fractionalOdds")
            if isinstance(f, dict):
                num = f.get("numerator")
                den = f.get("denominator")
                if isinstance(num, int) and isinstance(den, int):
                    fractional_val = f"{num}/{den}"
        # Parity invariant: both populated or both null
        if decimal_val is None or fractional_val is None:
            decimal_val = None
            fractional_val = None
        out.append(PaddyRunner(
            name=name,
            selection_id=selection_id,
            win_price=decimal_val,
            win_price_raw=fractional_val,
        ))
    return out


def _parse_eachway(market: dict) -> EachWayTerms | None:
    # Default True when field absent — parity with Kotlin parser
    available = market.get("eachwayAvailable", True)
    if available is False:
        return None
    places = market.get("numberOfPlaces")
    if not isinstance(places, int) or places <= 0:
        return None
    frac = market.get("placeFraction")
    if not isinstance(frac, dict):
        return None
    num = frac.get("numerator")
    den = frac.get("denominator")
    if not isinstance(num, int) or not isinstance(den, int) or den == 0:
        return None
    fraction = num / den
    if fraction <= 0.0 or fraction > 1.0:
        return None
    return EachWayTerms(fraction=fraction, places=places)


def _market_name(off_time_london: str, venue: str, race_type: str) -> str:
    # off_time_london is '2026-06-15T18:00:00+01:00'; pull out 'HH:mm'
    try:
        time_part = off_time_london[11:16]
    except IndexError:
        time_part = ""
    if race_type and race_type.strip():
        return f"{time_part} {venue} - {race_type.strip()}"
    return f"{time_part} {venue}"
