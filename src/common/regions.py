"""Region ids ↔ Betfair country codes. Pure, no I/O.

Region ids are stable lowercase CLI tokens (`gb-ie`, `us`). Country
codes follow Betfair's `event.countryCode` (`GB`, `IE`, `US`)."""

from __future__ import annotations

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us": frozenset({"US"}),
}

_VALID = ",".join(sorted(REGION_COUNTRIES))


def parse_regions(arg: str) -> frozenset[str]:
    """Parse a comma-separated region string into a set of region ids.

    Case-insensitive, whitespace-tolerant. Raises ValueError on an empty
    result or any unknown id (message lists the offenders and the valid set)."""
    ids = frozenset(
        part.strip().lower() for part in arg.split(",") if part.strip()
    )
    if not ids:
        raise ValueError(f"regions must be non-empty; valid: {_VALID}")
    unknown = sorted(ids - REGION_COUNTRIES.keys())
    if unknown:
        raise ValueError(
            f"unknown region(s) {','.join(unknown)}; valid: {_VALID}"
        )
    return ids


def countries_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of country codes for every region id. Assumes ids are valid
    (caller validates first via parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_COUNTRIES[rid]
    return frozenset(out)
