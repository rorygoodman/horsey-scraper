"""Region id → 888sport category slug(s). Pure, no I/O.

888's racing taxonomy groups by category slug, not Betfair country code:
`uk-and-ireland` covers GB+IE, `north-america` covers US (+Canada). This map
is 888-specific and deliberately separate from common.regions (country codes)."""

from __future__ import annotations

REGION_SLUGS: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"uk-and-ireland"}),
    "us": frozenset({"north-america"}),
}


def slugs_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of 888 category slugs for every region id. Assumes ids are
    valid (caller validates first via common.regions.parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_SLUGS.get(rid, frozenset())
    return frozenset(out)
