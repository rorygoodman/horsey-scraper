"""Validate a paddypower.json file against the schema.

Usage: python -m paddypower_scraper.validate [paddypower.json]
Exit 0 = valid, 1 = validation errors, 2 = file error."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_paddy_output


def main(argv: "list[str] | None" = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("paddypower.json")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    errors = validate_paddy_output(path.read_text())
    if not errors:
        print(f"{path}: VALID (matches spec)")
        return 0
    print(f"{path}: INVALID ({len(errors)} errors)")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
