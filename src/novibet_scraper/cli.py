"""Top-level orchestration for the Novibet scraper. Pure functions
everywhere except the BrowserSession side effect, which is injectable."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from common.regions import parse_regions
from common.timeutil import iso_utc
from paddypower_scraper.filtering import in_window, london_day_window

from . import api
from .browser import BrowserFetchError, BrowserSession
from .models import NovibetOutput, NovibetRace
from .output import write_novibet_json
from .overview import parse_overview
from .racecard import parse_racecard
from .regions import countries_for_all


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("novibet.json"),
) -> int:
    """Return exit code (0 = success/partial/empty, 1 = fetch error, 2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        wanted = countries_for_all(parse_regions(region_arg))
    except ValueError as e:
        print(f"novibet-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching Novibet day index for regions={region_arg}...")

    with make_session() as session:
        try:
            index_payload = session.fetch_json(api.OVERVIEW_URL)
        except BrowserFetchError as e:
            print(f"novibet: day index fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_overview(index_payload)
        in_region = [s for s in stubs if s.country in wanted]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        if not in_today:
            _write(out_path, now, [])
            print(f"Wrote {out_path} (0 races, 0 skipped)")
            return 0

        in_today.sort(key=lambda s: s.start_time_utc)

        races: list[NovibetRace] = []
        attempted = 0
        skipped = 0
        for stub in in_today:
            attempted += 1
            url = api.racecard_url(stub.bet_context_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                race = parse_racecard(payload, scraped_at,
                                      venue=stub.venue, country=stub.country)
            except BrowserFetchError as e:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: {e.reason}", file=sys.stderr)
                skipped += 1
                continue
            except Exception as e:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: parse error: {e}", file=sys.stderr)
                skipped += 1
                continue
            if race is None:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: no usable win market", file=sys.stderr)
                skipped += 1
                continue
            races.append(race)

        if attempted > 0 and not races:
            print("novibet: every attempted race failed", file=sys.stderr)
            return 1

        seen: set[tuple[str, str]] = set()
        deduped: list[NovibetRace] = []
        for r in races:
            key = (r.venue, r.off_time)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r.off_time)

        no_terms = 0
        for r in deduped:
            ew = r.each_way_terms
            if ew is None:
                no_terms += 1
                ew_str = "eachway=no"
            else:
                ew_str = f"eachway={ew.fraction:.2f} places={ew.places}"
            print(f"  {r.off_time[11:16]} {r.venue} → {len(r.runners)} runners, {ew_str}")

        meetings = len({r.venue for r in deduped})
        _write(out_path, now, deduped)
        print(f"Wrote {out_path} ({len(deduped)} races from {meetings} "
              f"meetings, {skipped} skipped, {no_terms} without each-way terms)")
        return 0


def _write(out_path: Path, now: datetime, races: list[NovibetRace]) -> None:
    write_novibet_json(
        NovibetOutput(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
