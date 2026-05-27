"""Golden round-trip: the validator accepts the sample, and
read→write→read is stable (guards float/int/key-order drift)."""

from __future__ import annotations

import json
from pathlib import Path

from betfair_scraper.models import ScrapeOutput, write_betfair_json
from betfair_scraper.validation import validate_scrape_output

FIXTURE = Path(__file__).parent / "fixtures" / "betfair_sample.json"


def test_sample_passes_validator():
    assert validate_scrape_output(FIXTURE.read_text()) == []


def test_round_trip_stable(tmp_path: Path):
    original = json.loads(FIXTURE.read_text())
    out = ScrapeOutput.from_dict(original)
    target = tmp_path / "betfair.json"
    write_betfair_json(out, target)
    reproduced = json.loads(target.read_text())
    assert reproduced == original


def test_selection_id_is_int_after_round_trip(tmp_path: Path):
    out = ScrapeOutput.from_dict(json.loads(FIXTURE.read_text()))
    target = tmp_path / "betfair.json"
    write_betfair_json(out, target)
    sel = json.loads(target.read_text())["races"][0]["runners"][0]["selectionId"]
    assert isinstance(sel, int)
