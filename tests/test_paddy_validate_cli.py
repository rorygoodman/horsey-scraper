"""Tests for `python -m paddypower_scraper.validate`."""

from __future__ import annotations

from paddypower_scraper.validate import main


def _write_valid(path):
    path.write_text(
        '{"scrapedAt":"2026-05-25T17:05:58Z","raceCount":0,"races":[]}'
    )


def test_valid_file_exit_0(tmp_path, capsys):
    f = tmp_path / "paddypower.json"
    _write_valid(f)
    assert main([str(f)]) == 0
    assert "VALID" in capsys.readouterr().out


def test_invalid_file_exit_1(tmp_path):
    f = tmp_path / "paddypower.json"
    f.write_text('{"scrapedAt":"nope","raceCount":0,"races":[]}')
    assert main([str(f)]) == 1


def test_missing_file_exit_2(tmp_path):
    assert main([str(tmp_path / "nope.json")]) == 2
