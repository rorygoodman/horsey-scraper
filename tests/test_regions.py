"""Tests for common.regions: parse region ids and map them to countries."""

from __future__ import annotations

import pytest

from common.regions import REGION_COUNTRIES, countries_for_all, parse_regions


class TestParseRegions:
    def test_single_gb_ie(self):
        assert parse_regions("gb-ie") == frozenset({"gb-ie"})

    def test_single_us(self):
        assert parse_regions("us") == frozenset({"us"})

    def test_combo(self):
        assert parse_regions("gb-ie,us") == frozenset({"gb-ie", "us"})

    def test_case_insensitive_and_whitespace(self):
        assert parse_regions(" GB-IE ,  US ") == frozenset({"gb-ie", "us"})

    def test_dedupes(self):
        assert parse_regions("us,us") == frozenset({"us"})

    def test_unknown_region_raises_with_valid_list(self):
        with pytest.raises(ValueError, match="valid: gb-ie,us"):
            parse_regions("xx")

    def test_unknown_region_names_offender(self):
        with pytest.raises(ValueError, match="xx"):
            parse_regions("gb-ie,xx")

    def test_empty_arg_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("   ")

    def test_commas_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions(",, ,")


class TestCountriesForAll:
    def test_gb_ie(self):
        assert countries_for_all(frozenset({"gb-ie"})) == frozenset({"GB", "IE"})

    def test_us(self):
        assert countries_for_all(frozenset({"us"})) == frozenset({"US"})

    def test_union(self):
        assert countries_for_all(frozenset({"gb-ie", "us"})) == frozenset(
            {"GB", "IE", "US"}
        )


class TestRegionTable:
    def test_table(self):
        assert REGION_COUNTRIES == {
            "gb-ie": frozenset({"GB", "IE"}),
            "us": frozenset({"US"}),
        }
