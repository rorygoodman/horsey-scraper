"""Top-level orchestration. Pure functions everywhere except the
BrowserSession side effect, which is injectable for tests."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

from . import api
from .browser import BrowserFetchError, BrowserSession
from .filtering import in_window, london_day_window
from common.regions import countries_for_all, parse_regions
from common.timeutil import iso_utc
from .meetings import parse_meetings_index
from .models import PaddyOutput, PaddyRace, RaceStub
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

        meetings = _group_by_meeting(in_today)
        if not meetings:
            # Legitimate empty day: write empty output and exit 0.
            _write(out_path, now, [])
            print(
                f"Wrote {out_path} (0 races from 0 meetings, 0 skipped)"
            )
            return 0

        all_races: list[PaddyRace] = []
        skipped = 0
        attempted = 0
        for meeting_id, stubs_in_meeting in meetings.items():
            attempted += 1
            anchor = stubs_in_meeting[0]
            url = api.racing_page_url(anchor.race_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                meeting_races = parse_meeting_response(payload, scraped_at)
            except BrowserFetchError as e:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: {e.reason}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            except Exception as e:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: parse error: {e}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            if not meeting_races:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: no usable races",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            for r in meeting_races:
                ew = r.each_way_terms
                ew_str = (
                    f"eachway={ew.fraction:.2f} places={ew.places}"
                    if ew else "eachway=no"
                )
                print(f"  {r.off_time[11:16]} {r.venue} ({meeting_id}) "
                      f"→ {len(r.runners)} runners, {ew_str}")
            all_races.extend(meeting_races)

        if attempted > 0 and not all_races:
            # Every attempted meeting failed.
            print("paddy: every attempted meeting failed", file=sys.stderr)
            return 1

        all_races.sort(key=lambda r: r.off_time)
        _write(out_path, now, all_races)
        print(
            f"Wrote {out_path} ({len(all_races)} races from "
            f"{attempted - skipped} meetings, {skipped} skipped)"
        )
        return 0


def _group_by_meeting(stubs: Iterable[RaceStub]) -> dict[str, list[RaceStub]]:
    groups: dict[str, list[RaceStub]] = {}
    for s in stubs:
        groups.setdefault(s.meeting_id, []).append(s)
    for v in groups.values():
        v.sort(key=lambda s: s.start_time_utc)
    # Deterministic meeting order: earliest race first.
    return dict(sorted(groups.items(), key=lambda kv: kv[1][0].start_time_utc))


def _write(out_path: Path, now: datetime, races: list[PaddyRace]) -> None:
    write_paddypower_json(
        PaddyOutput(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
