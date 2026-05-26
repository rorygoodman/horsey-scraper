"""PaddyPower endpoint constants and URL builders. No I/O."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.paddypower.com/horse-racing"

# Captured 2026-05-26 from the meetings-results tab probe. Card id 63 is
# PaddyPower's "all today's meetings index" — see design spec appendix.
MEETINGS_INDEX_URL = (
    "https://apisms.paddypower.com/smspp/content-managed-page/v7"
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl"
    "&cardsToFetch=63&countryCode=IE&currencyCode=EUR&eventTypeId=7"
    "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false"
    "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true"
    "&language=en&layoutFetchedCardsOnly=true&loggedIn=false"
    "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE"
    "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY"
    "&timezone=Europe%2FDublin"
)

_RACING_PAGE_BASE = (
    "https://apisms.paddypower.com/smspp/racing-page/v7"
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl"
    "&currencyCode=EUR&eventTypeId=7&exchangeLocale=en_GB"
    "&includePrices=true&includeRaceTimeform=true&includeResults=true"
    "&language=en&priceHistory=3&regionCode=IRE"
)


def racing_page_url(race_id: str) -> str:
    """Build a racing-page/v7 URL for the meeting containing this raceId.

    One call returns every race in the meeting with WIN markets at top
    level (`races`, `markets`). raceId is any race in the meeting."""
    return f"{_RACING_PAGE_BASE}&raceId={quote(race_id, safe='.')}"
