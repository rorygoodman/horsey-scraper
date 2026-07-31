"""Novibet endpoint constants and URL builders. No I/O.

Both feeds sit behind Cloudflare: a bare request is answered with a 403
challenge page, so browser.py warms up on WARMUP_URL first and then fetches
from inside the page. The x-gw-* headers are required by the gateway."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-IE"
TIMEZONE = "Europe/Dublin"

_BASE = "https://www.novibet.ie"
_SPORT_ID = "4324"           # horse racing
_GROUP_ID = "4372612"        # HORSE_RACING market-view group
_QUERY = "?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE"

# Warmup page — clears Cloudflare and seeds the session cookies.
WARMUP_URL = f"{_BASE}/sports/horse-racing/{_GROUP_ID}"

# Full-day index: days → countries → meetings → races.
OVERVIEW_URL = (
    f"{_BASE}/spt/feed/marketviews/horse-racing-overview2/"
    f"{_SPORT_ID}/{_GROUP_ID}{_QUERY}&timestamp=undefined"
)

_RACECARD_BASE = f"{_BASE}/spt/feed/marketviews/horse-racing-race2/{_SPORT_ID}/"

API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "x-gw-domain-key": "_IE",
    "x-gw-cms-key": "_IE",
    "x-gw-application-name": "NoviIE",
    "x-gw-currency-sysname": "EUR",
    "x-gw-country-sysname": "IE",
    "x-gw-language-sysname": "en-IE",
    "x-gw-client-timezone": "Europe/Dublin",
    "x-gw-channel": "WebPC",
    "x-gw-client-layout": "Desktop",
    "x-gw-odds-representation": "Fractional",
}


def racecard_url(bet_context_id: str) -> str:
    """Build a racecard URL for one Novibet betContextId."""
    return f"{_RACECARD_BASE}{quote(str(bet_context_id), safe='')}{_QUERY}"
