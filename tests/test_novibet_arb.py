"""arb_finder --source novibet: name+time join to Betfair -> novibethorses.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arb_finder import cli

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _write_inputs(tmp_path: Path, *, places: int = 3, fraction: float = 0.2):
    (tmp_path / "betfair.json").write_text(json.dumps({
        "scrapedAt": "2026-07-31T11:59:01Z",
        "raceCount": 1,
        "races": [{
            "raceId": "1.1", "venue": "Wolverhampton", "country": "GB",
            "offTime": "2026-07-31T14:00:00+01:00",
            "winMarketUrl": "https://www.betfair.com/exchange/plus/horse-racing/market/1.1",
            "marketName": "14:00 Wolverhampton",
            "marketScrapedAt": {"WIN": "2026-07-31T11:59:02Z",
                                "TOP_3": "2026-07-31T11:59:02Z",
                                "TOP_4": "2026-07-31T11:59:02Z"},
            "runners": [{"name": "Marianne Mozart",
                         "lay": {"WIN": 16.0, "TOP_3": 4.1, "TOP_4": 3.2},
                         "selectionId": 12345678}],
        }],
    }))
    (tmp_path / "novibet.json").write_text(json.dumps({
        "scrapedAt": "2026-07-31T11:59:07Z",
        "raceCount": 1,
        "races": [{
            "venue": "Wolverhampton", "country": "GB",
            # same instant as Betfair's +01:00 off time
            "offTime": "2026-07-31T13:00:00+00:00",
            "marketName": "Race Winner", "scrapedAt": "2026-07-31T11:59:07Z",
            "eachWayTerms": {"fraction": fraction, "places": places},
            "runners": [{"name": "Marianne Mozart",
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    }))


def _run(tmp_path: Path) -> int:
    return cli.main(["--source", "novibet",
                     str(tmp_path / "betfair.json"),
                     str(tmp_path / "novibet.json"),
                     str(tmp_path / "novibethorses.json")],
                    now=lambda: NOW)


def test_writes_novibethorses_with_a_novibet_leg(tmp_path: Path):
    _write_inputs(tmp_path)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horseCount"] == 1
    assert "novibetScrapedAt" in data
    horse = data["horses"][0]
    assert horse["novibet"]["winPrice"] == 15.0
    assert horse["novibet"]["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    # venue/country/ids come from the matched Betfair race
    assert horse["betfairWinMarketId"] == "1.1"
    assert horse["runner"]["selectionId"] == 12345678
    assert horse["betfair"]["placeMarket"] == "TOP_3"


def test_four_places_selects_top_4(tmp_path: Path):
    _write_inputs(tmp_path, places=4)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horses"][0]["betfair"]["placeMarket"] == "TOP_4"


def test_six_places_is_unpriceable_and_yields_no_horses(tmp_path: Path):
    # Betfair's to-be-placed markets stop at TOP_5.
    _write_inputs(tmp_path, places=6)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horseCount"] == 0


def test_output_passes_the_horses_schema(tmp_path: Path):
    # The bookie-aware validator from the unification refactor is what lets
    # novibethorses.json be schema-checked at all.
    from arb_finder.bookies import NOVIBET
    from arb_finder.validation import validate_horses_output

    _write_inputs(tmp_path)
    assert _run(tmp_path) == 0
    text = (tmp_path / "novibethorses.json").read_text()
    assert validate_horses_output(text, bookie=NOVIBET) == []


def test_empty_output_passes_the_horses_schema(tmp_path: Path):
    from arb_finder.bookies import NOVIBET
    from arb_finder.validation import validate_horses_output

    _write_inputs(tmp_path, places=6)  # unpriceable → zero horses
    assert _run(tmp_path) == 0
    text = (tmp_path / "novibethorses.json").read_text()
    assert validate_horses_output(text, bookie=NOVIBET) == []


def test_missing_input_exits_2(tmp_path: Path):
    assert cli.main(["--source", "novibet",
                     str(tmp_path / "nope.json"),
                     str(tmp_path / "also-nope.json"),
                     str(tmp_path / "out.json")], now=lambda: NOW) == 2


def test_defaults_resolve_to_novibet_filenames(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No positional args → betfair.json + novibet.json → novibethorses.json.
    # Inputs are absent, so this exits 2 having looked for the right names.
    assert cli.main(["--source", "novibet"], now=lambda: NOW) == 2
