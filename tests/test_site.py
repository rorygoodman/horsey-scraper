"""Tests guarding the static site: the sample data stays schema-valid and
index.html references the fields it renders. (The page/script themselves are
verified by manual preview + end-to-end publish.)"""

from __future__ import annotations

from pathlib import Path

from arb_finder.validation import validate_horses_output

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "horses.example.json"


def test_example_validates():
    assert validate_horses_output(EXAMPLE.read_text()) == []


INDEX = ROOT / "index.html"


def test_index_references_schema_fields():
    html = INDEX.read_text()
    assert "horses.json" in html
    for field in ("computedAt", "horseCount", "edge", "winPrice",
                  "winLay", "placeLay", "placeMarket"):
        assert field in html, f"index.html missing reference to {field!r}"
