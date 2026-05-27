"""Tests for the arb_finder CLI (writes horses.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arb_finder.cli import main, parse_horses_cli_args


class TestParseArgs:
    def test_defaults(self):
        assert parse_horses_cli_args([]) == ("betfair.json", "paddypower.json", "horses.json")

    def test_explicit(self):
        assert parse_horses_cli_args(["a", "b", "c"]) == ("a", "b", "c")

    def test_bad_arity(self):
        with pytest.raises(ValueError):
            parse_horses_cli_args(["only-one"])


def _write_betfair(path: Path):
    # WIN lay 4.0 + TOP_2 lay 3.0 → a NEGATIVE edge (proves no filtering).
    path.write_text(json.dumps({
        "scrapedAt": "2026-05-25T17:05:56.890289Z", "raceCount": 1,
        "races": [{
            "raceId": "1.1", "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "winMarketUrl": "u",
            "marketName": "18:00 Ascot",
            "marketScrapedAt": {"WIN": "2026-05-25T17:05:58Z",
                                "TOP_2": "2026-05-25T17:05:58Z"},
            "runners": [{"name": "A", "lay": {"WIN": 4.0, "TOP_2": 3.0},
                         "selectionId": 1}],
        }],
    }))


def _write_paddy(path: Path):
    path.write_text(json.dumps({
        "scrapedAt": "2026-05-25T17:05:58.384555Z", "raceCount": 1,
        "races": [{
            "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "marketName": "18:00 Ascot",
            "raceUrl": "r", "scrapedAt": "2026-05-25T17:05:58.384555Z",
            "betfairWinMarketId": "1.1",
            "eachWayTerms": {"fraction": 0.2, "places": 2},
            "runners": [{"name": "A", "selectionId": 1,
                         "winPrice": 2.0, "winPriceRaw": "1/1"}],
        }],
    }))


def test_happy_path_writes_horses_including_negative_edge(tmp_path: Path):
    bf = tmp_path / "betfair.json"; _write_betfair(bf)
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    out = tmp_path / "horses.json"
    rc = main([str(bf), str(pp), str(out)],
              now=lambda: datetime(2026, 5, 25, 17, 6, 8, tzinfo=timezone.utc))
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["horseCount"] == 1
    assert payload["horses"][0]["runner"]["selectionId"] == 1
    assert payload["horses"][0]["edge"] < 0  # kept despite negative edge
    assert payload["betfairScrapedAt"] == "2026-05-25T17:05:56.890289Z"


def test_missing_input_exits_2(tmp_path: Path):
    assert main([str(tmp_path / "nope.json"), str(tmp_path / "nope2.json"),
                 str(tmp_path / "horses.json")]) == 2


def test_invalid_betfair_exits_2(tmp_path: Path):
    bf = tmp_path / "betfair.json"; bf.write_text('{"scrapedAt":"nope","raceCount":0,"races":[]}')
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    assert main([str(bf), str(pp), str(tmp_path / "horses.json")]) == 2


def test_bad_arity_exits_1(tmp_path: Path):
    assert main(["only-one"]) == 1
