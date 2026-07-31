"""Parse a horse-racing-race2 response into one NovibetRace.

Two things to know about this payload:

1. Each-way terms come from the caption of the EACHWAY market category, NOT
   its sysname. The sysname looks like <places>_<divisor> and usually is,
   but on Place Boost races it keeps the base terms while the caption
   advertises the boosted ones actually on offer (5 of 30 GB/IRE races on
   the capture day disagreed). There is no sysname fallback: a wrong
   fraction or place count misprices every runner in the race, always in
   the direction of phantom arbs.

2. The win market already excludes non-runners — `horses[]` carries the
   full card with horseStatus, the win market only the actual runners. We
   iterate the win market and additionally drop anything flagged
   NonRunner, so a change at either end cannot leak one through."""

from __future__ import annotations

import re
import sys

from .models import EachWayTerms, NovibetRace, NovibetRunner

WIN_CATEGORY = "HORSE_RACING_MAIN"
EACHWAY_PREFIX = "HORSE_RACING_RACE_WINNER_EACHWAY_"
MARKET_NAME = "Race Winner"

# "E/W 1/5 - 3 Places" and "Place Boost 1/5 - 4 Places" both match. The
# (?<!\d) guard stops the leading "1" matching mid-number (e.g. "11/5"),
# which would otherwise silently parse as 1/5 instead of failing loudly.
_TERMS_RE = re.compile(
    r"(?<!\d)1\s*/\s*(\d+)\s*-\s*(\d+)\s*places?", re.IGNORECASE
)


def parse_each_way_caption(caption: str) -> "EachWayTerms | None":
    """Extract terms from a market-category caption. None if unparseable."""
    if not isinstance(caption, str):
        return None
    m = _TERMS_RE.search(caption)
    if m is None:
        return None
    divisor = int(m.group(1))
    places = int(m.group(2))
    if divisor <= 0 or places <= 0:
        return None
    fraction = 1.0 / divisor
    if not (0.0 < fraction <= 1.0):
        return None
    return EachWayTerms(fraction=fraction, places=places)


def parse_racecard(
    payload: dict, scraped_at_utc: str, *, venue: str, country: str
) -> "NovibetRace | None":
    """Build a NovibetRace, or None when the payload carries no usable win
    market (race at/after the off, or a malformed response)."""
    if not isinstance(payload, dict):
        return None
    off_time = payload.get("startDateTime")
    if not (isinstance(off_time, str) and off_time):
        return None
    categories = payload.get("marketCategories")
    if not isinstance(categories, list) or not categories:
        return None

    non_runners = _non_runner_names(payload.get("horses"))
    runners = _parse_runners(_category(categories, WIN_CATEGORY), non_runners)
    if not runners:
        return None

    return NovibetRace(
        venue=venue,
        country=country,
        off_time=off_time,
        market_name=MARKET_NAME,
        scraped_at=scraped_at_utc,
        each_way_terms=_parse_eachway(categories),
        runners=runners,
    )


def _category(categories: list, sysname: str) -> "dict | None":
    for c in categories:
        if isinstance(c, dict) and c.get("sysname") == sysname:
            return c
    return None


def _parse_eachway(categories: list) -> "EachWayTerms | None":
    for c in categories:
        if not isinstance(c, dict):
            continue
        sysname = c.get("sysname")
        if isinstance(sysname, str) and sysname.startswith(EACHWAY_PREFIX):
            caption = c.get("caption")
            terms = parse_each_way_caption(caption)
            if terms is None:
                print(
                    f"Unparseable each-way caption {caption!r} for category "
                    f"{sysname!r} — Novibet may have changed the caption "
                    f"format",
                    file=sys.stderr,
                )
            return terms
    return None


def _non_runner_names(horses: object) -> set:
    if not isinstance(horses, list):
        return set()
    out = set()
    for h in horses:
        if not isinstance(h, dict):
            continue
        name = h.get("horseName")
        if isinstance(name, str) and name and h.get("horseStatus") != "Runner":
            out.add(name)
    return out


def _bet_items(category: "dict | None") -> list:
    if not isinstance(category, dict):
        return []
    for item in category.get("items") or []:
        if not isinstance(item, dict):
            continue
        for view in item.get("betViews") or []:
            if isinstance(view, dict) and isinstance(view.get("betItems"), list):
                return view["betItems"]
    return []


def _parse_runners(category: "dict | None", non_runners: set) -> list[NovibetRunner]:
    out: list[NovibetRunner] = []
    for b in _bet_items(category):
        if not isinstance(b, dict):
            continue
        name = b.get("caption")
        if not (isinstance(name, str) and name) or name in non_runners:
            continue
        price = _to_float(b.get("price"))
        raw = b.get("oddsText")
        raw = raw if isinstance(raw, str) and raw else None
        if b.get("isAvailable") is not True or price is None or price <= 0.0 \
                or raw is None:
            price = None
            raw = None
        out.append(NovibetRunner(name=name, win_price=price, win_price_raw=raw))
    return out


def _to_float(v: object) -> "float | None":
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
