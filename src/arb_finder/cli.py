"""Edge calculator entry point. Reads + validates betfair.json and one
bookie's scrape, prices every fully-priced runner, writes that bookie's
horses file. Exit 0 ok (even zero horses), 1 bad usage, 2 input error."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from betfair_scraper.models import ScrapeOutput
from betfair_scraper.validation import validate_scrape_output
from common.timeutil import iso_utc
from paddypower_scraper.models import PaddyOutput
from paddypower_scraper.validation import validate_paddy_output
from sport888_scraper.models import Sport888Output
from sport888_scraper.validation import validate_sport888_output

from .bookies import Bookie, PADDYPOWER, SPORT888
from .calculator import find_horses, find_horses_by_name
from .models import BookieHorsesOutput, write_bookie_horses_json


@dataclass(frozen=True)
class SourceSpec:
    bookie: Bookie
    label: str                              # for error messages
    parse: Callable[[str], Any]             # JSON text -> bookie output model
    validate: Callable[[str], list[str]]    # JSON text -> schema errors
    join: str                               # "ids" | "name"


SOURCES: dict[str, SourceSpec] = {
    "paddypower": SourceSpec(
        bookie=PADDYPOWER, label="PaddyPower",
        parse=lambda t: PaddyOutput.from_dict(json.loads(t)),
        validate=validate_paddy_output, join="ids"),
    "888": SourceSpec(
        bookie=SPORT888, label="888sport",
        parse=lambda t: Sport888Output.from_dict(json.loads(t)),
        validate=validate_sport888_output, join="name"),
}


def parse_cli_args(spec: SourceSpec, argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", spec.bookie.default_bookie_input,
                spec.bookie.default_output)
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    flag = "" if spec.bookie.key == "paddypower" else f" --source {spec.bookie.key}"
    raise ValueError(
        f"usage: arb-finder{flag}"
        f"                                # all defaults\n"
        f"       arb-finder{flag} <betfair-in> <bookie-in> <out>  # all explicit"
    )


def main(argv=None, *, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = "paddypower"
    if "--source" in argv:
        i = argv.index("--source")
        try:
            source = argv[i + 1]
        except IndexError:
            print(f"--source requires a value ({'|'.join(SOURCES)})", file=sys.stderr)
            return 1
        del argv[i:i + 2]
    spec = SOURCES.get(source)
    if spec is None:
        print(f"unknown --source {source}; valid: {', '.join(SOURCES)}",
              file=sys.stderr)
        return 1
    return _run(spec, argv, now)


def _run(spec: SourceSpec, argv: list[str], now) -> int:
    try:
        betfair_in, bookie_in, out_path = parse_cli_args(spec, argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    bookie_text = _read_or_none(bookie_in)
    if bookie_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    bookie_errors = spec.validate(bookie_text)
    if bookie_errors:
        print(f"Error: {bookie_in} fails {spec.label} schema:", file=sys.stderr)
        for e in bookie_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    bookie_out = spec.parse(bookie_text)

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    if spec.join == "ids":
        horses = find_horses(betfair, bookie_out)
        stats = None
    else:
        horses, stats = find_horses_by_name(betfair, bookie_out)

    output = BookieHorsesOutput(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        bookie_scraped_at=bookie_out.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_bookie_horses_json(output, spec.bookie, out_path)

    if stats is None:
        print(f"Wrote {out_path} ({len(horses)} horses from "
              f"{len(betfair.races)} BF races and "
              f"{len(bookie_out.races)} PP races)")
    else:
        print(f"Wrote {out_path} ({len(horses)} horses; races matched "
              f"{stats.races_matched}/"
              f"{stats.races_matched + stats.races_unmatched}, "
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
