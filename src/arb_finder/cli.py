"""Edge calculator entry point. Reads + validates betfair.json and
paddypower.json, prices every fully-priced runner, writes horses.json.
Exit 0 ok (even zero horses), 1 bad usage, 2 input error."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from betfair_scraper.models import ScrapeOutput
from betfair_scraper.validation import validate_scrape_output
from common.timeutil import iso_utc
from paddypower_scraper.models import PaddyOutput
from paddypower_scraper.validation import validate_paddy_output
from .calculator import find_horses
from .models import HorsesOutput, write_horses_json
from sport888_scraper.models import Sport888Output
from sport888_scraper.validation import validate_sport888_output
from .calculator import find_horses_by_name
from .models import Horses888Output, write_horses888_json


def parse_horses_cli_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", "paddypower.json", "horses.json")
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    raise ValueError(
        "usage: arb-finder                                          # all defaults\n"
        "       arb-finder <betfair-in> <paddypower-in> <horses-out>  # all explicit"
    )


def main(argv=None, *, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = "paddypower"
    if "--source" in argv:
        i = argv.index("--source")
        try:
            source = argv[i + 1]
        except IndexError:
            print("--source requires a value (paddypower|888)", file=sys.stderr)
            return 1
        del argv[i:i + 2]
    if source not in ("paddypower", "888"):
        print(f"unknown --source {source}; valid: paddypower, 888", file=sys.stderr)
        return 1
    if source == "888":
        return _run_888(argv, now)
    return _run_paddypower(argv, now)


def _run_paddypower(argv, now) -> int:
    # ---- existing main() body, unchanged ----
    try:
        betfair_in, paddy_in, out_path = parse_horses_cli_args(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    paddy_text = _read_or_none(paddy_in)
    if paddy_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    paddy_errors = validate_paddy_output(paddy_text)
    if paddy_errors:
        print(f"Error: {paddy_in} fails PaddyPower schema:", file=sys.stderr)
        for e in paddy_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    paddy = PaddyOutput.from_dict(json.loads(paddy_text))

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    horses = find_horses(betfair, paddy)
    output = HorsesOutput(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        paddypower_scraped_at=paddy.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_horses_json(output, out_path)
    print(f"Wrote {out_path} ({len(horses)} horses from {len(betfair.races)} BF races "
          f"and {len(paddy.races)} PP races)")
    return 0


def parse_888_cli_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", "888sport.json", "888horses.json")
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    raise ValueError(
        "usage: arb-finder --source 888                                    # defaults\n"
        "       arb-finder --source 888 <betfair-in> <888sport-in> <out>   # explicit"
    )


def _run_888(argv, now) -> int:
    try:
        betfair_in, eight88_in, out_path = parse_888_cli_args(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    eight88_text = _read_or_none(eight88_in)
    if eight88_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    eight88_errors = validate_sport888_output(eight88_text)
    if eight88_errors:
        print(f"Error: {eight88_in} fails 888sport schema:", file=sys.stderr)
        for e in eight88_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    eight88 = Sport888Output.from_dict(json.loads(eight88_text))

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    horses, stats = find_horses_by_name(betfair, eight88)
    output = Horses888Output(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        sport888_scraped_at=eight88.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_horses888_json(output, out_path)
    print(f"Wrote {out_path} ({len(horses)} horses; "
          f"races matched {stats.races_matched}/{stats.races_matched + stats.races_unmatched}, "
          f"runners unmatched {stats.runners_unmatched})")
    return 0


def _read_or_none(path: str) -> "str | None":
    p = Path(path)
    if not p.exists():
        print(f"Error: input file not found: {path}", file=sys.stderr)
        return None
    try:
        return p.read_text()
    except OSError as e:
        print(f"Error: failed to read {path}: {e}", file=sys.stderr)
        return None
