"""William Hill racing-API endpoint constants and URL builders. No I/O.

The meetings SPA reads a plain public JSON API (no auth, no bot wall), so
client.py fetches it directly over HTTPS. `rmp01` is the en-gb horse-racing
service id the SPA hard-codes."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

_BASE = (
    "https://sports.williamhill.com/data/rmp01/api/v2/"
    "desktop/horse-racing/en-gb"
)

# Today's index: region → competitions (meetings) → events (races).
DAY_INDEX_URL = f"{_BASE}/region-competitions/all/today"

API_HEADERS = {
    "accept": "application/json",
    "user-agent": USER_AGENT,
}


def event_url(event_id: str) -> str:
    """Build a racecard URL for one William Hill event id (OB_EV…)."""
    return f"{_BASE}/events/{quote(str(event_id), safe='')}"
