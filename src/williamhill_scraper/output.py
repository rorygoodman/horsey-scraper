"""Serialize WilliamHillOutput to williamhill.json with camelCase keys,
atomic write. Delegates to common.jsonio.write_json."""

from __future__ import annotations

from pathlib import Path

from common.jsonio import write_json

from .models import WilliamHillOutput

WILLIAMHILL_RENAME = {
    "each_way_terms": "eachWayTerms",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "off_time": "offTime",
    "market_name": "marketName",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_williamhill_json(out: WilliamHillOutput, path: Path | str) -> None:
    write_json(out, WILLIAMHILL_RENAME, path)
