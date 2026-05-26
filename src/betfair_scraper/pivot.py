"""Pivot per-market scrapes into per-runner lay maps. Port of RunnerPivot.kt.

WIN absent → []. Each runner's lay map has exactly the keys present in
`scrapes` (declared MarketType order). A runner missing from a scraped
market maps that key to None. Runners in a Top-N but not WIN are dropped
with a stderr warning."""

from __future__ import annotations

import sys

from common.markettype import MarketType
from .models import MarketScrape, RunnerOdds


def pivot_market_scrapes(
    scrapes: dict[MarketType, MarketScrape], race_id_for_warnings: str
) -> list[RunnerOdds]:
    win = scrapes.get(MarketType.WIN)
    if win is None:
        return []

    win_names = {r.name for r in win.runners}
    ordered = [t for t in MarketType if t in scrapes]

    for t in ordered:
        if t is MarketType.WIN:
            continue
        for entry in scrapes[t].runners:
            if entry.name not in win_names:
                print(
                    f"Phantom horse '{entry.name}' in {t.name} for race "
                    f"{race_id_for_warnings} — dropping",
                    file=sys.stderr,
                )

    out: list[RunnerOdds] = []
    for win_entry in win.runners:
        lay: dict[MarketType, float | None] = {}
        for t in ordered:
            entry = next(
                (r for r in scrapes[t].runners if r.name == win_entry.name), None
            )
            lay[t] = entry.lay if entry is not None else None
        out.append(
            RunnerOdds(name=win_entry.name, lay=lay, selection_id=win_entry.selection_id)
        )
    return out
