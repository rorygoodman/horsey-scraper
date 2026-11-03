"""Validate a williamhill.json payload string against the schema.

Delegates to the shared bookie-scrape validator; William Hill requires no
race-level string fields beyond the common set."""

from __future__ import annotations

from common.scrapevalidation import validate_bookie_scrape


def validate_williamhill_output(text: str) -> list[str]:
    return validate_bookie_scrape(text)
