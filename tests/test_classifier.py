"""Tests for betfair_scraper.classifier."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.classifier import classify_top_n


def test_ui_name_form():
    assert classify_top_n("Top 3 Finish", None) is MarketType.TOP_3


def test_api_name_form():
    assert classify_top_n("3 TBP", None) is MarketType.TOP_3


def test_case_insensitive_and_trimmed():
    assert classify_top_n("  top 2 FINISH  ", None) is MarketType.TOP_2


def test_to_be_placed_rejected():
    assert classify_top_n("To Be Placed", None) is None


def test_winners_mismatch_rejected():
    assert classify_top_n("Top 3 Finish", 4) is None


def test_winners_match_accepted():
    assert classify_top_n("Top 3 Finish", 3) is MarketType.TOP_3


def test_out_of_range_name():
    assert classify_top_n("Top 6 Finish", None) is None
    assert classify_top_n("1 TBP", None) is None
