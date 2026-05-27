"""Top-level orchestration. Pure functions everywhere except the
BrowserSession side effect, which is injectable for tests."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from . import api
from .browser import BrowserFetchError, BrowserSession
from .filtering import in_window, london_day_window
from common.regions import countries_for_all, parse_regions
from common.timeutil import iso_utc
from .meetings import parse_meetings_index
from .models import PaddyOutput, PaddyRace
from .output import write_paddypower_json
from .races import parse_meeting_response


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("paddypower.json"),
) -> int:
    """Return process exit code (0 = success or partial, 1 = fetch error,
    2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        countries = countries_for_all(parse_regions(region_arg))
    except ValueError as e:
        print(f"paddypower-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching PaddyPower meetings for regions={region_arg}...")

    with make_session() as session:
        # Index fetch — catastrophic if it fails.
        try:
            index_payload = session.fetch_json(api.MEETINGS_INDEX_URL)
        except BrowserFetchError as e:
            print(f"paddy: meetings index fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_meetings_index(index_payload)
        in_region = [s for s in stubs if s.country_code in countries]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        if not in_today:
            # Legitimate empty day: write empty output and exit 0.
            _write(out_path, now, [])
            print(
                f"Wrote {out_path} (0 races from 0 meetings, 0 skipped)"
            )
            return 0

        in_today.sort(key=lambda s: s.start_time_utc)

        # Per-race fan-out. A racing-page response lists the whole meeting's
        # race metadata but includes the market for ONLY the requested raceId,
        # so one call per meeting yields just one race. The index already
        # gives us every race's raceId, so we fetch racing-page per race.
        all_races: list[PaddyRace] = []
        attempted = 0
        skipped = 0
        for stub in in_today:
            attempted += 1
            url = api.racing_page_url(stub.race_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                races = parse_meeting_response(payload, scraped_at)
            except BrowserFetchError as e:
                print(
                    f"paddy: skipping race {stub.race_id} {stub.venue}: {e.reason}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            except Exception as e:
                print(
                    f"paddy: skipping race {stub.race_id} {stub.venue}: parse error: {e}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            if not races:
                print(
                    f"paddy: skipping race {stub.race_id} {stub.venue}: no usable race",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            all_races.extend(races)

        if attempted > 0 and not all_races:
            # Every attempted race failed.
            print("paddy: every attempted race failed", file=sys.stderr)
            return 1

        # Each racing-page call carries only the requested race's market, so it
        # yields exactly that race; dedup by (venue, off_time) guards against
        # any cross-call market bleed.
        seen: set[tuple[str, str]] = set()
        deduped: list[PaddyRace] = []
        for r in all_races:
            key = (r.venue, r.off_time)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r.off_time)

        for r in deduped:
            ew = r.each_way_terms
            ew_str = (
                f"eachway={ew.fraction:.2f} places={ew.places}"
                if ew else "eachway=no"
            )
            print(f"  {r.off_time[11:16]} {r.venue} "
                  f"→ {len(r.runners)} runners, {ew_str}")

        meetings_represented = len({r.venue for r in deduped})
        _write(out_path, now, deduped)
        print(
            f"Wrote {out_path} ({len(deduped)} races from "
            f"{meetings_represented} meetings, {skipped} skipped)"
        )
        return 0


def _write(out_path: Path, now: datetime, races: list[PaddyRace]) -> None:
    write_paddypower_json(
        PaddyOutput(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
