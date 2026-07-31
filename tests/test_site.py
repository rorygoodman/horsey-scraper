"""Tests guarding the static site: the sample data stays schema-valid and
index.html references the fields it renders. (The page/script themselves are
verified by manual preview + end-to-end publish.)"""

from __future__ import annotations

import os
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


def test_index_offers_888_source():
    # The bookie source toggle reads 888horses.json and its sport888 leg.
    html = INDEX.read_text()
    assert "888horses.json" in html, "index.html missing 888horses.json source"
    assert "sport888" in html, "index.html missing sport888 bookie leg"


def test_publish_script_shape():
    sh = ROOT / "publish.sh"
    assert sh.exists(), "publish.sh missing"
    assert os.access(sh, os.X_OK), "publish.sh not executable"
    text = sh.read_text()
    for token in ("./run.sh", "index.html", "horses.json", "gh-pages", "push -f"):
        assert token in text, f"publish.sh missing {token!r}"


def test_publish_script_copies_888horses():
    text = (ROOT / "publish.sh").read_text()
    assert "888horses.json" in text, "publish.sh should copy 888horses.json to the site"


def test_index_offers_novibet_source():
    html = INDEX.read_text()
    assert "novibethorses.json" in html, "index.html missing novibethorses.json source"
    assert "novibet" in html, "index.html missing novibet bookie leg"


def test_publish_script_copies_novibethorses():
    text = (ROOT / "publish.sh").read_text()
    assert "novibethorses.json" in text, \
        "publish.sh should copy novibethorses.json to the site"
