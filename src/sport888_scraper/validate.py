"""CLI: validate an 888sport.json file. `python -m sport888_scraper.validate <path>`."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_sport888_output


def main(argv: "list[str] | None" = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python -m sport888_scraper.validate <888sport.json>",
              file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text()
    except OSError as e:
        print(f"cannot read {argv[0]}: {e}", file=sys.stderr)
        return 2
    errors = validate_sport888_output(text)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
