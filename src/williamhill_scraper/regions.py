"""Region id → William Hill region-filter id(s). Pure, no I/O.

William Hill's day index groups meetings by its own region filters rather
than by country, and does not split GB from IE. `us-canada` also carries
Canadian tracks; those simply find no Betfair match downstream. This map is
William Hill-specific and deliberately separate from common.regions."""

from __future__ import annotations

REGION_FILTERS: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"uk-ireland"}),
    "us": frozenset({"us-canada"}),
}


def filters_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of William Hill region-filter ids for every region id. Assumes
    ids are valid (caller validates first via common.regions.parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_FILTERS.get(rid, frozenset())
    return frozenset(out)
