"""Parse an events/<id> response into one WilliamHillRace.

Three things to know about this payload:

1. The main win market is the single "Win" market of the "Racecard"
   collection. The "Each Way Extra" collection carries *other* markets
   (more places at shorter prices) and is ignored, as is the in-play
   "Win - In Play" market under inPlayRaceCardData.

2. Each-way terms are read from the market's structured fields
   (eachWayFactorNum/Den, eachWayPlaces) and cross-checked against its
   caption ("EW: 1/5 Odds 4 Places"). On Extra Places races both already
   carry the boosted terms (all 76 GB/IE + US races on the capture day
   agreed). If they ever disagree the terms are dropped, never guessed: a
   wrong fraction or place count misprices every runner in the race, always
   toward phantom arbs. "Win Only" races (1/1, 1 place) have no terms.

3. Non-runners stay on the card with active=false and a suspended
   selection that still holds its last price. They are dropped outright so
   a stale price can never be priced against Betfair."""

from __future__ import annotations

import re
import sys

from common.timeutil import utc_to_london

from .models import EachWayTerms, WilliamHillRace, WilliamHillRunner
from .times import to_iso_utc

RACECARD_COLLECTION = "Racecard"
WIN_MARKET = "Win"
MARKET_NAME = "Win"

_CAPTION_RE = re.compile(
    r"(?<!\d)(\d+)\s*/\s*(\d+)\s*odds\s*(\d+)\s*places?", re.IGNORECASE
)


def parse_each_way_caption(caption: object) -> "tuple[int, int, int] | None":
    """'EW: 1/5 Odds 3 Places' → (1, 5, 3). None if unparseable."""
    if not isinstance(caption, str):
        return None
    m = _CAPTION_RE.search(caption)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def each_way_terms(market: dict) -> "EachWayTerms | None":
    """Terms from the market's structured fields, confirmed by its caption."""
    num = market.get("eachWayFactorNum")
    den = market.get("eachWayFactorDen")
    places = market.get("eachWayPlaces")
    if not all(isinstance(v, int) and not isinstance(v, bool)
               for v in (num, den, places)):
        return None
    if places <= 1 or num <= 0 or den <= 0:
        return None  # "Win Only"
    fraction = num / den
    if not (0.0 < fraction < 1.0):
        return None
    caption = market.get("eachWay")
    if parse_each_way_caption(caption) != (num, den, places):
        print(
            f"Each-way caption {caption!r} disagrees with structured terms "
            f"{num}/{den} {places} places — William Hill may have changed "
            f"the payload; dropping terms",
            file=sys.stderr,
        )
        return None
    return EachWayTerms(fraction=fraction, places=places)


def parse_racecard(
    payload: dict, scraped_at_utc: str, *, venue: str, country: str
) -> "WilliamHillRace | None":
    """Build a WilliamHillRace, or None when the payload carries no usable
    win market (race at/after the off, or a malformed response)."""
    if not isinstance(payload, dict):
        return None
    event = payload.get("event")
    if not isinstance(event, dict):
        return None
    start = to_iso_utc(event.get("startDateTime"))
    off_time = utc_to_london(start) if start else None
    if off_time is None:
        return None

    card = payload.get("raceCardData")
    if not isinstance(card, dict):
        return None
    collection = _collection(card.get("marketCollections"))
    market = _win_market(collection)
    if market is None:
        return None

    runners = _parse_runners(collection, market["id"],
                             card.get("selections"), event.get("runners"))
    if not runners:
        return None

    return WilliamHillRace(
        venue=venue,
        country=country,
        off_time=off_time,
        market_name=MARKET_NAME,
        scraped_at=scraped_at_utc,
        each_way_terms=each_way_terms(market),
        runners=runners,
    )


def _collection(collections: object) -> "dict | None":
    if not isinstance(collections, list):
        return None
    for c in collections:
        if isinstance(c, dict) and c.get("name") == RACECARD_COLLECTION:
            return c
    return None


def _win_market(collection: "dict | None") -> "dict | None":
    if not isinstance(collection, dict):
        return None
    wins = [m for m in collection.get("markets") or []
            if isinstance(m, dict) and m.get("name") == WIN_MARKET
            and isinstance(m.get("id"), str)]
    return wins[0] if len(wins) == 1 else None


def _parse_runners(
    collection: dict, market_id: str, selections: object, runners: object
) -> list[WilliamHillRunner]:
    selections = selections if isinstance(selections, dict) else {}
    runners = runners if isinstance(runners, dict) else {}
    out: list[WilliamHillRunner] = []
    for table in collection.get("raceCardTables") or []:
        if not isinstance(table, dict):
            continue
        for row in table.get("raceCardRows") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("title")
            if not (isinstance(name, str) and name):
                continue
            runner = runners.get(row.get("runnerId"))
            if row.get("active") is not True or (
                    isinstance(runner, dict) and runner.get("active") is False):
                continue  # non-runner
            out.append(_priced(name, _win_selection(row, market_id, selections)))
    return out


def _win_selection(row: dict, market_id: str, selections: dict) -> "dict | None":
    for sid in row.get("selections") or []:
        sel = selections.get(sid)
        if isinstance(sel, dict) and sel.get("marketId") == market_id:
            return sel
    return None


def _priced(name: str, sel: "dict | None") -> WilliamHillRunner:
    num = sel.get("priceNum") if sel else None
    den = sel.get("priceDen") if sel else None
    if (sel is None or sel.get("status") != "A"
            or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0
                       for v in (num, den))):
        return WilliamHillRunner(name=name, win_price=None, win_price_raw=None)
    return WilliamHillRunner(name=name, win_price=num / den + 1.0,
                             win_price_raw=f"{num}/{den}")
