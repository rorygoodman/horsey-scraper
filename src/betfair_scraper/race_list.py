"""Today's WIN markets in the selected regions. Port of RaceListFetcher.kt."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from common.regions import countries_for_all
from common.timeutil import LONDON, iso_utc
from .models import Race
from .responses import build_catalogue_body, race_from_catalogue


def london_day_window_utc(day: date) -> tuple[str, str]:
    """(from_utc, to_utc) ISO-'Z' strings for the 24h London day on `day`."""
    start = datetime.combine(day, time(0, 0), tzinfo=LONDON)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=LONDON)
    return iso_utc(start), iso_utc(end)


def parse_catalogue_races(text: str) -> list[Race]:
    """Shred a listMarketCatalogue array into Races. Skips unparseable
    entries, dedupes by raceId (first wins), sorts by (offTime, venue)."""
    arr = json.loads(text)
    out: list[Race] = []
    seen: set[str] = set()
    for el in arr:
        if not isinstance(el, dict):
            continue
        race = race_from_catalogue(el)
        if race is None or race.race_id in seen:
            continue
        seen.add(race.race_id)
        out.append(race)
    out.sort(key=lambda r: (r.off_time, r.venue))
    return out


class RaceListFetcher:
    def __init__(self, client):
        self.client = client

    def fetch(self, regions: frozenset[str], today: "date | None" = None) -> list[Race]:
        if today is None:
            today = datetime.now(LONDON).date()
        from_, to = london_day_window_utc(today)
        countries = sorted(countries_for_all(regions))
        body = build_catalogue_body(
            market_type_codes=["WIN"],
            countries=countries,
            from_=from_,
            to=to,
            projection=["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
            max_results=1000,
            sort="FIRST_TO_START",
        )
        return parse_catalogue_races(self.client.list_market_catalogue(body))
