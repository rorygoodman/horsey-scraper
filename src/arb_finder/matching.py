"""Structural match of a bookie race/runner to a Betfair race/runner.

888sport carries no Betfair ids, so we match by off-time instant + normalized
venue (race) and normalized runner name (selection). Exact normalized matches
only — no fuzzy matching, because a wrong match yields a silently mispriced arb."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from betfair_scraper.models import RaceOdds, RunnerOdds


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def normalize_name(name: str) -> str:
    """Lowercase, strip accents to ASCII, drop all non-alphanumerics."""
    return _fold(name)


def normalize_venue(venue: str) -> str:
    """Same folding as names — drops '(AW)', '(July)', spaces, punctuation."""
    return _fold(venue)


def to_instant(iso: str) -> "datetime | None":
    """Parse an ISO string to a UTC datetime, or None if unparseable."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def match_race(
    off_time: str, venue: str, betfair_races: list[RaceOdds]
) -> "RaceOdds | None":
    """Match by off-time instant + normalized venue. Falls back to the unique
    Betfair race at that instant when venue names disagree. Returns None when
    no candidate or when ambiguous."""
    inst = to_instant(off_time)
    if inst is None:
        return None
    same = [r for r in betfair_races if to_instant(r.off_time) == inst]
    if not same:
        return None
    v = normalize_venue(venue)
    vmatch = [r for r in same if normalize_venue(r.venue) == v]
    if len(vmatch) == 1:
        return vmatch[0]
    if not vmatch and len(same) == 1:
        return same[0]
    return None


def match_runner(name: str, race: RaceOdds) -> "RunnerOdds | None":
    """Match a runner by exact normalized name. None if absent or ambiguous."""
    n = normalize_name(name)
    matches = [r for r in race.runners if normalize_name(r.name) == n]
    return matches[0] if len(matches) == 1 else None
