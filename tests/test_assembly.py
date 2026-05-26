"""Tests for betfair_scraper.assembly."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.assembly import assemble_race_odds, format_market_name
from betfair_scraper.models import MarketScrape, Race, RunnerEntry


def _race():
    return Race("1.1", "Ballinrobe", "IE", "2026-05-25T18:05:00+01:00",
                "https://x/market/1.1")


def test_format_with_race_type():
    assert format_market_name(_race(), "2m1f Beg Chs") == "18:05 Ballinrobe - 2m1f Beg Chs"


def test_format_without_race_type():
    assert format_market_name(_race(), "  ") == "18:05 Ballinrobe"


def test_assemble_requires_win():
    scrapes = {MarketType.TOP_2: MarketScrape(MarketType.TOP_2, "2026-05-25T17:00:00Z", [])}
    assert assemble_race_odds(_race(), "name", scrapes) is None


def test_assemble_builds_race_odds():
    scrapes = {
        MarketType.WIN: MarketScrape(MarketType.WIN, "2026-05-25T17:00:00Z",
                                     [RunnerEntry(1, "A", 2.0)]),
    }
    odds = assemble_race_odds(_race(), "18:05 Ballinrobe", scrapes)
    assert odds.race_id == "1.1"
    assert list(odds.market_scraped_at.keys()) == [MarketType.WIN]
    assert odds.runners[0].name == "A"
