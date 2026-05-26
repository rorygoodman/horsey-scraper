"""Serialize PaddyOutput to JSON with camelCase keys, atomic write."""

from __future__ import annotations

import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path

from .models import PaddyOutput

_SNAKE_TO_CAMEL = {
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


def _to_dict(obj):
    if is_dataclass(obj):
        out = {}
        for f in fields(obj):
            key = _SNAKE_TO_CAMEL.get(f.name, f.name)
            out[key] = _to_dict(getattr(obj, f.name))
        return out
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    return obj


def write_paddypower_json(out: PaddyOutput, path: Path) -> None:
    """Serialize `out` to `path` as JSON with camelCase keys.

    Atomic: writes to `{path}.tmp` then `os.replace`s into place. Same
    directory as `path`, so the rename is on one filesystem."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = _to_dict(out)
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
