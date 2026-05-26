"""The five lay markets we track. Enum member order defines JSON key order
(WIN first), so do not reorder."""

from __future__ import annotations

import enum


class MarketType(enum.Enum):
    WIN = "WIN"
    TOP_2 = "TOP_2"
    TOP_3 = "TOP_3"
    TOP_4 = "TOP_4"
    TOP_5 = "TOP_5"


def top_n_from_places(n: int) -> "MarketType | None":
    """Map a place count (2..5) to its TOP_N market; None outside 2..5."""
    return {
        2: MarketType.TOP_2,
        3: MarketType.TOP_3,
        4: MarketType.TOP_4,
        5: MarketType.TOP_5,
    }.get(n)
