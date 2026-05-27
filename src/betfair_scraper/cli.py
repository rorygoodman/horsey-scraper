"""Entry point: one pass over today's racing via the Betfair Exchange API.
Port of Main.kt. Returns process exit code (0 ok, 1 region/scrape error,
2 credentials error)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from common.regions import parse_regions
from common.timeutil import iso_utc
from .client import BetfairClient
from .credentials import default_credentials_path, load_credentials
from .models import ScrapeOutput, write_betfair_json
from .race_list import RaceListFetcher
from .race_odds import RaceOddsFetcher

OUTPUT_FILE = "betfair.json"


def main(argv=None, *, make_client=None, now=None, out_path: Path | str = OUTPUT_FILE) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        regions = parse_regions(argv[0]) if argv else parse_regions("gb-ie")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        creds = load_credentials(default_credentials_path())
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    run_start = (now or (lambda: datetime.now(timezone.utc)))()
    make_client = make_client or (lambda app_key: BetfairClient(app_key))

    print("Horsey Scraper — Betfair Exchange API — multi-market lay")
    print(f"regions={','.join(sorted(regions))}")
    print("=" * 80)

    client = make_client(creds.app_key)
    try:
        client.login(creds.username, creds.password)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"\n[{iso_utc(run_start)}] Fetching today's race list…")
    try:
        races = RaceListFetcher(client).fetch(regions)
    except Exception as e:
        print(f"Error fetching race list: {e}", file=sys.stderr)
        return 1
    print(f"Found {len(races)} races today.")
    for r in races:
        print(f"  {r.off_time}  {r.country}  {r.venue}  ({r.race_id})")

    try:
        results = RaceOddsFetcher(client, now=now).fetch(races, regions)
    except Exception as e:
        print(f"Error fetching odds: {e}", file=sys.stderr)
        return 1

    for odds in results:
        markets = ",".join(t.name for t in odds.market_scraped_at)
        print(f"  {odds.off_time} {odds.venue} ({odds.race_id}) → "
              f"{len(odds.runners)} runners, markets=[{markets}]")
    result_ids = {o.race_id for o in results}
    for r in races:
        if r.race_id not in result_ids:
            print(f"  {r.off_time} {r.venue} ({r.race_id}) DROPPED")

    output = ScrapeOutput(
        scraped_at=iso_utc(run_start), race_count=len(results), races=results)
    write_betfair_json(output, out_path)
    print(f"\nWrote {out_path} ({len(results)} races)")
    return 0
