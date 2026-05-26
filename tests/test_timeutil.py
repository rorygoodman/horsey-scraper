"""Tests for common.timeutil."""

from __future__ import annotations

from datetime import datetime, timezone

from common.timeutil import iso_utc, utc_to_london


class TestUtcToLondon:
    def test_bst_summer(self):
        # 17:05 UTC in May (BST, +01:00) → 18:05 local.
        assert utc_to_london("2026-05-25T17:05:00Z") == "2026-05-25T18:05:00+01:00"

    def test_gmt_winter(self):
        # 13:30 UTC in January (GMT, +00:00).
        assert utc_to_london("2026-01-15T13:30:00Z") == "2026-01-15T13:30:00Z"

    def test_accepts_offset_input(self):
        assert utc_to_london("2026-05-25T17:05:00+00:00") == "2026-05-25T18:05:00+01:00"

    def test_garbage_returns_none(self):
        assert utc_to_london("not-a-date") is None


class TestIsoUtc:
    def test_formats_z(self):
        dt = datetime(2026, 5, 25, 17, 5, 56, 890289, tzinfo=timezone.utc)
        assert iso_utc(dt) == "2026-05-25T17:05:56.890289Z"

    def test_converts_aware_to_utc(self):
        from zoneinfo import ZoneInfo

        dt = datetime(2026, 5, 25, 18, 5, 0, tzinfo=ZoneInfo("Europe/London"))
        assert iso_utc(dt) == "2026-05-25T17:05:00Z"
