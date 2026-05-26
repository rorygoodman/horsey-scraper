"""Tests for common.isovalid."""

from __future__ import annotations

from common.isovalid import is_iso_offset_datetime, is_iso_utc


class TestIsIsoUtc:
    def test_z_instant(self):
        assert is_iso_utc("2026-05-25T17:05:56.890289Z")

    def test_z_whole_second(self):
        assert is_iso_utc("2026-05-25T17:05:56Z")

    def test_offset_form_is_not_utc_instant(self):
        # An offset like +01:00 is a valid moment but not the 'Z' instant form.
        assert not is_iso_utc("2026-05-25T18:05:00+01:00")

    def test_garbage(self):
        assert not is_iso_utc("not-a-date")

    def test_empty(self):
        assert not is_iso_utc("")


class TestIsIsoOffsetDateTime:
    def test_bst_offset(self):
        assert is_iso_offset_datetime("2026-05-25T18:05:00+01:00")

    def test_z_offset(self):
        assert is_iso_offset_datetime("2026-01-15T13:30:00Z")

    def test_missing_offset(self):
        assert not is_iso_offset_datetime("2026-05-25T18:05:00")

    def test_garbage(self):
        assert not is_iso_offset_datetime("nope")
