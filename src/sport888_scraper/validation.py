"""Validate an 888sport.json payload string against the schema.

Mirrors paddypower_scraper.validation but drops raceUrl / betfairWinMarketId
(888 has no Betfair ids). Delegates to the shared bookie-scrape validator."""

from __future__ import annotations

from common.scrapevalidation import validate_bookie_scrape


def validate_sport888_output(text: str) -> list[str]:
    return validate_bookie_scrape(text)
