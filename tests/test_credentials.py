"""Tests for betfair_scraper.credentials."""

from __future__ import annotations

import os

import pytest

from betfair_scraper.credentials import (
    Credentials,
    load_credentials,
    parse_credentials,
)


class TestParse:
    def test_happy(self):
        c = parse_credentials('{"username":"u","password":"p","appKey":"k"}')
        assert c == Credentials("u", "p", "k")

    def test_ignores_extra_fields(self):
        c = parse_credentials('{"username":"u","password":"p","appKey":"k","x":1}')
        assert c.app_key == "k"

    def test_missing_fields_listed(self):
        with pytest.raises(ValueError, match="password,appKey"):
            parse_credentials('{"username":"u"}')

    def test_not_object(self):
        with pytest.raises(ValueError, match="not a valid object"):
            parse_credentials("[]")


class TestLoad:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            load_credentials(tmp_path / "nope.json")

    def test_loads_and_warns_when_world_readable(self, tmp_path, capsys):
        p = tmp_path / "credentials.json"
        p.write_text('{"username":"u","password":"p","appKey":"k"}')
        os.chmod(p, 0o644)
        c = load_credentials(p)
        assert c == Credentials("u", "p", "k")
        assert "chmod 600" in capsys.readouterr().err

    def test_no_warn_when_0600(self, tmp_path, capsys):
        p = tmp_path / "credentials.json"
        p.write_text('{"username":"u","password":"p","appKey":"k"}')
        os.chmod(p, 0o600)
        load_credentials(p)
        assert "chmod 600" not in capsys.readouterr().err
