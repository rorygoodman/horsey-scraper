"""888sport (spectate) endpoint constants and URL builders. No I/O."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/London"

# Warmup page — seeds the session cookies the spectate API requires
# (bare requests without cookies get 403).
WARMUP_URL = "https://www.888sport.com/horse-racing/"

# Full-day meetings index, grouped category → meeting → event ids.
SCHEDULE_URL = (
    "https://spectate-web.888sport.com/spectate/racing/"
    "getSchedule/horse-racing?tab=today"
)

_RACECARD_BASE = (
    "https://spectate-web.888sport.com/spectate/sportsbook-req/getRacecard/"
)


def racecard_url(event_id: str) -> str:
    """Build a getRacecard URL for one 888 event id."""
    return f"{_RACECARD_BASE}{quote(event_id, safe='')}"
