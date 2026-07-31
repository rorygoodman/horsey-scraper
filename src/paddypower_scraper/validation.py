"""Validate a paddypower.json payload string against the schema.

Port of PaddySchemaValidator.kt. Delegates to the shared bookie-scrape
validator; PaddyPower alone additionally requires a raceUrl string on each
race."""

from __future__ import annotations

from common.scrapevalidation import validate_bookie_scrape


def validate_paddy_output(text: str) -> list[str]:
    return validate_bookie_scrape(text, required_race_strings=("raceUrl",))
