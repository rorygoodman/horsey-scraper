"""Serialize PaddyOutput to JSON with camelCase keys, atomic write.

Delegates to common.jsonio.write_json for the actual serialization."""

from __future__ import annotations

from pathlib import Path

from common.jsonio import write_json

from .models import PaddyOutput

PADDY_RENAME = {
    "each_way_terms": "eachWayTerms",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "betfair_win_market_id": "betfairWinMarketId",
    "off_time": "offTime",
    "market_name": "marketName",
    "race_url": "raceUrl",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_paddypower_json(out: PaddyOutput, path: Path) -> None:
    """Serialize `out` to `path` as JSON with camelCase keys.

    Atomic: writes to `{path}.tmp` then `os.replace`s into place. Same
    directory as `path`, so the rename is on one filesystem."""
    write_json(out, PADDY_RENAME, path)
