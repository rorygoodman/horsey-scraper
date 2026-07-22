"""Opt-in live test hitting the real 888sport API. Enable with RUN_INTEGRATION=1.
Skipped by default so CI/unit runs need no network or browser."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

if not os.environ.get("RUN_INTEGRATION"):
    pytest.skip("integration test; set RUN_INTEGRATION=1 to run",
                allow_module_level=True)


def test_live_scrape_writes_valid_json(tmp_path: Path):
    from sport888_scraper import cli
    from sport888_scraper.validation import validate_sport888_output

    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], out_path=out)
    assert rc == 0, "live 888 scrape should succeed"
    text = out.read_text()
    assert validate_sport888_output(text) == []
    data = json.loads(text)
    assert data["raceCount"] == len(data["races"])
