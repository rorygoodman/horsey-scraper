"""Serialize NovibetOutput to novibet.json with camelCase keys, atomic
write. Delegates to common.jsonio.write_json."""

from __future__ import annotations

from pathlib import Path

from common.jsonio import write_json

from .models import NovibetOutput

NOVIBET_RENAME = {
    "each_way_terms": "eachWayTerms",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "off_time": "offTime",
    "market_name": "marketName",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_novibet_json(out: NovibetOutput, path: Path | str) -> None:
    write_json(out, NOVIBET_RENAME, path)
