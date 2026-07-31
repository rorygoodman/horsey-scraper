"""Tests for the shared bookie-scrape validator core (common.scrapevalidation),
covering the one thing that varies between bookies: required_race_strings.

These pin exactly what the per-bookie delegations in paddypower_scraper,
sport888_scraper and novibet_scraper rely on but do not themselves assert:
that PaddyPower alone requires raceUrl, and that it is checked between
marketName and scrapedAt. tests/test_paddy_validation.py,
tests/test_paddy_validate_cli.py and tests/test_sport888_validation.py stay
untouched — this file is additive."""

from __future__ import annotations

import json

from common.scrapevalidation import validate_bookie_scrape
from novibet_scraper.validation import validate_novibet_output
from paddypower_scraper.validation import validate_paddy_output
from sport888_scraper.validation import validate_sport888_output


def _race(**overrides) -> dict:
    """A race object with every field the shared validator can check,
    present and clean, unless overridden or explicitly omitted."""
    race = {
        "venue": "Ballinrobe",
        "country": "IE",
        "offTime": "2026-05-25T18:05:00+01:00",
        "marketName": "18:05 Ballinrobe",
        "raceUrl": "https://www.paddypower.com/...",
        "scrapedAt": "2026-05-25T17:05:58Z",
        "eachWayTerms": None,
        "runners": [],
    }
    race.update(overrides)
    return race


def _payload(race: dict) -> str:
    return json.dumps({
        "scrapedAt": "2026-05-25T17:05:58Z",
        "raceCount": 1,
        "races": [race],
    })


def _without(race: dict, *keys: str) -> dict:
    race = dict(race)
    for k in keys:
        race.pop(k, None)
    return race


def test_paddypower_requires_raceurl():
    """Fails if required_race_strings is ever emptied for PaddyPower."""
    payload = _payload(_without(_race(), "raceUrl"))
    errors = validate_paddy_output(payload)
    assert any("raceUrl" in e for e in errors)


def test_888_and_novibet_do_not_require_raceurl():
    """Pins the difference in the other direction: adding raceUrl to
    everyone's required set would not be caught by test_paddypower_requires_
    raceurl alone, but is caught here."""
    payload = _payload(_without(_race(), "raceUrl"))
    assert validate_sport888_output(payload) == []
    assert validate_novibet_output(payload) == []


def test_raceurl_error_is_ordered_between_marketname_and_scrapedat():
    """Fails if a future edit moves the required_race_strings loop to a
    different position in validate_bookie_scrape (e.g. before marketName or
    after scrapedAt), even if raceUrl is still required somewhere."""
    payload = _payload(
        _without(_race(), "marketName", "raceUrl", "scrapedAt")
    )
    errors = validate_paddy_output(payload)
    assert errors == [
        "marketName: missing or not string",
        "raceUrl: missing or not string",
        "scrapedAt: missing or not string",
    ]


def test_required_race_strings_is_honoured_generically():
    """Exercises validate_bookie_scrape directly (not through any bookie
    delegation) so the parameter itself is proven to work, independent of
    which bookie currently uses it."""
    payload = _payload(_without(_race(), "raceUrl"))
    clean = validate_bookie_scrape(payload)
    assert clean == []  # no extra requirement -> no complaint

    errors = validate_bookie_scrape(
        payload, required_race_strings=("someField",)
    )
    assert any("someField" in e for e in errors)
