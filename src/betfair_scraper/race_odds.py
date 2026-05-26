"""Fetch WIN + classified Top-N markets and join into RaceOdds.
Port of RaceOddsFetcher.kt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from common.markettype import MarketType
from common.regions import countries_for_all
from common.timeutil import LONDON, iso_utc
from .assembly import assemble_race_odds, format_market_name
from .classifier import classify_top_n
from .models import MarketScrape, Race, RaceOdds, RunnerEntry
from .race_list import london_day_window_utc
from .responses import (
    MarketBookSnapshot,
    MarketBookStatus,
    build_book_body,
    build_catalogue_body,
    lay_prices_from_book,
)


@dataclass(frozen=True)
class PlaceMarketEntry:
    market_id: str
    type: MarketType
    event_id: str
    market_time: str
    runners: dict[int, str]


def chunk_of_40(items: list) -> list[list]:
    return [items[i:i + 40] for i in range(0, len(items), 40)] if items else []


def _runner_map(catalogue: dict) -> dict[int, str]:
    runners = catalogue.get("runners")
    out: dict[int, str] = {}
    if not isinstance(runners, list):
        return out
    for r in runners:
        if not isinstance(r, dict):
            continue
        sel, name = r.get("selectionId"), r.get("runnerName")
        if isinstance(sel, int) and not isinstance(sel, bool) and isinstance(name, str):
            out[sel] = name
    return out


def parse_catalogue_place_markets(text: str) -> list[PlaceMarketEntry]:
    arr = json.loads(text)
    out: list[PlaceMarketEntry] = []
    for el in arr:
        if not isinstance(el, dict):
            continue
        name = el.get("marketName")
        desc = el.get("description")
        if not isinstance(name, str) or not isinstance(desc, dict):
            continue
        n_winners = desc.get("numberOfWinners")
        if not isinstance(n_winners, int) or isinstance(n_winners, bool):
            n_winners = None
        type_ = classify_top_n(name, n_winners)
        if type_ is None:
            continue
        market_time = desc.get("marketTime")
        market_id = el.get("marketId")
        event = el.get("event")
        if not isinstance(market_time, str) or not isinstance(market_id, str) \
                or not isinstance(event, dict):
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str):
            continue
        out.append(PlaceMarketEntry(market_id, type_, event_id, market_time, _runner_map(el)))
    return out


def place_markets_by_race_id(
    entries: list[PlaceMarketEntry],
    race_key_by_race_id: dict[str, tuple[str, str]],
) -> dict[str, list[PlaceMarketEntry]]:
    race_id_by_key = {key: rid for rid, key in race_key_by_race_id.items()}
    out: dict[str, list[PlaceMarketEntry]] = {}
    for entry in entries:
        rid = race_id_by_key.get((entry.event_id, entry.market_time))
        if rid is None:
            continue
        out.setdefault(rid, []).append(entry)
    return out


def parse_win_catalogue_runners(text: str) -> dict[str, list[tuple[int, str]]]:
    arr = json.loads(text)
    out: dict[str, list[tuple[int, str]]] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        market_id = el.get("marketId")
        runners = el.get("runners")
        if not isinstance(market_id, str) or not isinstance(runners, list):
            continue
        pairs: list[tuple[int, str]] = []
        for r in runners:
            if not isinstance(r, dict):
                continue
            sel, name = r.get("selectionId"), r.get("runnerName")
            if isinstance(sel, int) and not isinstance(sel, bool) and isinstance(name, str):
                pairs.append((sel, name))
        out[market_id] = pairs
    return out


def parse_book_snapshots(text: str) -> dict[str, MarketBookSnapshot]:
    arr = json.loads(text)
    out: dict[str, MarketBookSnapshot] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        market_id = el.get("marketId")
        if isinstance(market_id, str):
            out[market_id] = lay_prices_from_book(el)
    return out


def parse_win_race_types(text: str) -> dict[str, str]:
    arr = json.loads(text)
    out: dict[str, str] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        mid = el.get("marketId")
        if isinstance(mid, str):
            name = el.get("marketName")
            out[mid] = name if isinstance(name, str) else ""
    return out


def parse_win_race_keys(text: str) -> dict[str, tuple[str, str]]:
    arr = json.loads(text)
    out: dict[str, tuple[str, str]] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        mid = el.get("marketId")
        event = el.get("event")
        if not isinstance(mid, str) or not isinstance(event, dict):
            continue
        eid = event.get("id")
        mst = el.get("marketStartTime")
        if isinstance(eid, str) and isinstance(mst, str):
            out[mid] = (eid, mst)
    return out


def join_scrapes(
    races: list[Race],
    place_markets: dict[str, list[PlaceMarketEntry]],
    snapshots: dict[str, MarketBookSnapshot],
    win_runners: dict[str, list[tuple[int, str]]],
    win_market_name: str,
    scraped_at: str,
) -> list[RaceOdds]:
    out: list[RaceOdds] = []
    for race in races:
        win_snap = snapshots.get(race.race_id)
        if win_snap is None or win_snap.status is not MarketBookStatus.OPEN:
            continue
        name_order = win_runners.get(race.race_id)
        if name_order is None:
            continue
        scrapes: dict[MarketType, MarketScrape] = {
            MarketType.WIN: MarketScrape(
                type=MarketType.WIN,
                scraped_at=scraped_at,
                runners=[
                    RunnerEntry(selection_id=sel, name=name,
                                lay=win_snap.lay_by_selection_id.get(sel))
                    for sel, name in name_order
                ],
            )
        }
        for place in place_markets.get(race.race_id, []):
            snap = snapshots.get(place.market_id)
            if snap is None or snap.status is not MarketBookStatus.OPEN:
                continue
            scrapes[place.type] = MarketScrape(
                type=place.type,
                scraped_at=scraped_at,
                runners=[
                    RunnerEntry(selection_id=sel, name=name,
                                lay=snap.lay_by_selection_id.get(sel))
                    for sel, name in place.runners.items()
                ],
            )
        odds = assemble_race_odds(race, win_market_name, scrapes)
        if odds is not None:
            out.append(odds)
    return out


class RaceOddsFetcher:
    def __init__(self, client, now=None):
        self.client = client
        self._now = now

    def _now_utc(self) -> datetime:
        if self._now is not None:
            return self._now()
        return datetime.now(timezone.utc)

    def fetch(self, races: list[Race], regions: frozenset[str]) -> list[RaceOdds]:
        if not races:
            return []
        countries = sorted(countries_for_all(regions))
        from_, to = london_day_window_utc(datetime.now(LONDON).date())

        place_json = self.client.list_market_catalogue(build_catalogue_body(
            market_type_codes=["PLACE", "OTHER_PLACE"], countries=countries,
            from_=from_, to=to,
            projection=["EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"],
            max_results=1000, sort="FIRST_TO_START"))
        place_entries = parse_catalogue_place_markets(place_json)

        win_json = self.client.list_market_catalogue(build_catalogue_body(
            market_type_codes=["WIN"], countries=countries, from_=from_, to=to,
            projection=["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION",
                        "RUNNER_DESCRIPTION"],
            max_results=1000, sort="FIRST_TO_START"))
        win_runners = parse_win_catalogue_runners(win_json)
        win_race_types = parse_win_race_types(win_json)
        race_keys = parse_win_race_keys(win_json)

        place_by_race = place_markets_by_race_id(place_entries, race_keys)

        all_ids = list(dict.fromkeys(
            [r.race_id for r in races]
            + [pm.market_id for lst in place_by_race.values() for pm in lst]))
        snapshots: dict[str, MarketBookSnapshot] = {}
        for chunk in chunk_of_40(all_ids):
            snapshots.update(parse_book_snapshots(
                self.client.list_market_book(build_book_body(chunk))))

        scraped_at = iso_utc(self._now_utc())

        out: list[RaceOdds] = []
        for race in races:
            market_name = format_market_name(race, win_race_types.get(race.race_id, ""))
            out.extend(join_scrapes(
                races=[race],
                place_markets={race.race_id: place_by_race.get(race.race_id, [])},
                snapshots=snapshots, win_runners=win_runners,
                win_market_name=market_name, scraped_at=scraped_at))
        return out
