"""Classify a Betfair market name into a TOP_N MarketType. Port of
MarketClassifier.kt. Accepts the UI form 'Top N Finish' and the REST API
form 'N TBP', N in 2..5."""

from __future__ import annotations

import re

from common.markettype import MarketType

_UI = re.compile(r"top ([2-5]) finish", re.IGNORECASE)
_API = re.compile(r"([2-5]) tbp", re.IGNORECASE)


def classify_top_n(name: str, number_of_winners: "int | None") -> "MarketType | None":
    trimmed = name.strip()
    m = _UI.fullmatch(trimmed) or _API.fullmatch(trimmed)
    if m is None:
        return None
    n = int(m.group(1))
    if number_of_winners is not None and number_of_winners != n:
        return None
    return {2: MarketType.TOP_2, 3: MarketType.TOP_3,
            4: MarketType.TOP_4, 5: MarketType.TOP_5}.get(n)
