"""Region id → Novibet country caption(s). Pure, no I/O.

Novibet's day index groups by its own country captions, which are close to
but not identical to Betfair's country codes: Novibet says "IRE" and "USA"
where Betfair says "IE" and "US". This map is Novibet-specific and
deliberately separate from common.regions."""

from __future__ import annotations

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IRE"}),
    "us": frozenset({"USA"}),
}


def countries_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of Novibet country captions for every region id. Assumes ids
    are valid (caller validates first via common.regions.parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_COUNTRIES.get(rid, frozenset())
    return frozenset(out)
