"""Tests for betfair_scraper.pivot."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.models import MarketScrape, RunnerEntry
from betfair_scraper.pivot import pivot_market_scrapes


def _scrape(t, runners):
    return MarketScrape(type=t, scraped_at="2026-05-25T17:00:00Z", runners=runners)


def test_win_absent_returns_empty():
    scrapes = {MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(1, "A", 1.5)])}
    assert pivot_market_scrapes(scrapes, "1.1") == []


def test_lay_keys_match_scraped_markets_in_order():
    scrapes = {
        MarketType.WIN: _scrape(MarketType.WIN, [RunnerEntry(1, "A", 2.0), RunnerEntry(2, "B", 3.0)]),
        MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(1, "A", 1.5)]),
    }
    out = pivot_market_scrapes(scrapes, "1.1")
    assert [r.name for r in out] == ["A", "B"]
    assert list(out[0].lay.keys()) == [MarketType.WIN, MarketType.TOP_2]
    # B not in TOP_2 → None for that key
    assert out[1].lay == {MarketType.WIN: 3.0, MarketType.TOP_2: None}
    assert out[0].selection_id == 1


def test_phantom_horse_warns(capsys):
    scrapes = {
        MarketType.WIN: _scrape(MarketType.WIN, [RunnerEntry(1, "A", 2.0)]),
        MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(9, "Ghost", 1.1)]),
    }
    out = pivot_market_scrapes(scrapes, "1.42")
    assert [r.name for r in out] == ["A"]  # Ghost dropped (not in WIN)
    assert "Phantom horse 'Ghost' in TOP_2 for race 1.42" in capsys.readouterr().err
