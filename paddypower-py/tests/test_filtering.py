"""Tests for filtering.py: region parsing, London-day window, in-window check."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from paddypower_scraper.filtering import (
    REGION_COUNTRIES,
    in_window,
    london_day_window,
    parse_regions,
)


class TestParseRegions:
    def test_single_gb_ie(self):
        assert parse_regions("gb-ie") == frozenset({"GB", "IE"})

    def test_single_us(self):
        assert parse_regions("us") == frozenset({"US"})

    def test_combo(self):
        assert parse_regions("gb-ie,us") == frozenset({"GB", "IE", "US"})

    def test_whitespace_tolerant(self):
        assert parse_regions(" gb-ie ,  us ") == frozenset({"GB", "IE", "US"})

    def test_unknown_region_raises(self):
        with pytest.raises(ValueError, match="valid: gb-ie,us"):
            parse_regions("xx")

    def test_empty_arg_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("   ")


class TestLondonDayWindow:
    def test_bst_summer(self):
        # 2026-06-15 10:00 UTC = 11:00 BST. End-of-London-day = 23:00 UTC.
        now = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        start, end = london_day_window(now)
        assert start == now
        assert end == datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc)

    def test_gmt_winter(self):
        # 2026-12-15 10:00 UTC = 10:00 GMT. End-of-London-day = 24:00 UTC.
        now = datetime(2026, 12, 15, 10, 0, tzinfo=timezone.utc)
        start, end = london_day_window(now)
        assert start == now
        assert end == datetime(2026, 12, 16, 0, 0, tzinfo=timezone.utc)

    def test_just_before_midnight_bst(self):
        # 22:30 UTC in June = 23:30 BST. End is still today London = 23:00 UTC.
        now = datetime(2026, 6, 15, 22, 30, tzinfo=timezone.utc)
        _, end = london_day_window(now)
        # Window may be in the past, but the spec says "midnight of tomorrow London".
        # 23:30 BST → tomorrow London midnight = 2026-06-16 00:00 BST = 2026-06-15 23:00 UTC.
        assert end == datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc)


class TestInWindow:
    def test_race_inside_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert in_window("2026-06-15T15:00:00.000Z", win)

    def test_race_at_start_inclusive(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert in_window("2026-06-15T10:00:00.000Z", win)

    def test_race_at_end_exclusive(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-15T23:00:00.000Z", win)

    def test_race_before_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-15T09:59:59.000Z", win)

    def test_race_after_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-16T00:00:00.000Z", win)


class TestRegionCountries:
    def test_table_matches_kotlin(self):
        # Parity with Kotlin Regions.kt
        assert REGION_COUNTRIES == {
            "gb-ie": frozenset({"GB", "IE"}),
            "us": frozenset({"US"}),
        }
