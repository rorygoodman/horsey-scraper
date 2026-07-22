"""Top-level orchestration for the 888sport scraper. Pure functions
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
from .models import Sport888Output, Sport888Race
from .output import write_sport888_json
from .racecard import parse_racecard
from .regions import slugs_for_all
from .schedule import parse_schedule


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("888sport.json"),
) -> int:
    """Return exit code (0 = success/partial/empty, 1 = fetch error, 2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        wanted_slugs = slugs_for_all(parse_regions(region_arg))
    except ValueError as e:
        print(f"sport888-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching 888sport schedule for regions={region_arg}...")

    with make_session() as session:
        try:
            index_payload = session.fetch_json(api.SCHEDULE_URL)
        except BrowserFetchError as e:
            print(f"888: schedule fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_schedule(index_payload)
        in_region = [s for s in stubs if s.category_slug in wanted_slugs]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        if not in_today:
            _write(out_path, now, [])
            print(f"Wrote {out_path} (0 races, 0 skipped)")
            return 0

        in_today.sort(key=lambda s: s.start_time_utc)

        races: list[Sport888Race] = []
        attempted = 0
        skipped = 0
        for stub in in_today:
            attempted += 1
            url = api.racecard_url(stub.event_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                race = parse_racecard(payload, scraped_at)
            except BrowserFetchError as e:
                print(f"888: skipping race {stub.event_id} {stub.venue}: {e.reason}",
                      file=sys.stderr)
                skipped += 1
                continue
            except Exception as e:
                print(f"888: skipping race {stub.event_id} {stub.venue}: parse error: {e}",
                      file=sys.stderr)
                skipped += 1
                continue
            if race is None:
                print(f"888: skipping race {stub.event_id} {stub.venue}: no usable race",
                      file=sys.stderr)
                skipped += 1
                continue
            races.append(race)

        if attempted > 0 and not races:
            print("888: every attempted race failed", file=sys.stderr)
            return 1

        seen: set[tuple[str, str]] = set()
        deduped: list[Sport888Race] = []
        for r in races:
            key = (r.venue, r.off_time)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r.off_time)

        for r in deduped:
            ew = r.each_way_terms
            ew_str = (f"eachway={ew.fraction:.2f} places={ew.places}"
                      if ew else "eachway=no")
            print(f"  {r.off_time[11:16]} {r.venue} → {len(r.runners)} runners, {ew_str}")

        meetings = len({r.venue for r in deduped})
        _write(out_path, now, deduped)
        print(f"Wrote {out_path} ({len(deduped)} races from {meetings} "
              f"meetings, {skipped} skipped)")
        return 0


def _write(out_path: Path, now: datetime, races: list[Sport888Race]) -> None:
    write_sport888_json(
        Sport888Output(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
