"""Tests for common.markettype."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places


def test_member_names_and_values_match():
    assert [m.name for m in MarketType] == ["WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"]
    assert all(m.value == m.name for m in MarketType)


def test_declaration_order_is_win_first():
    # Output key order depends on this; WIN must come first.
    assert list(MarketType)[0] is MarketType.WIN


def test_top_n_from_places():
    assert top_n_from_places(2) is MarketType.TOP_2
    assert top_n_from_places(3) is MarketType.TOP_3
    assert top_n_from_places(4) is MarketType.TOP_4
    assert top_n_from_places(5) is MarketType.TOP_5


def test_top_n_from_places_out_of_range():
    assert top_n_from_places(1) is None
    assert top_n_from_places(6) is None
    assert top_n_from_places(0) is None
