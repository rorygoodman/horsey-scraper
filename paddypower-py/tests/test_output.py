"""Tests for output.py: write paddypower.json with camelCase keys."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)
from paddypower_scraper.output import write_paddypower_json


def _sample_output() -> PaddyOutput:
    return PaddyOutput(
        scraped_at="2026-05-26T18:00:00Z",
        race_count=1,
        races=[PaddyRace(
            venue="Plumpton",
            country="GB",
            off_time="2026-05-26T18:39:00+01:00",
            market_name="18:39 Plumpton - 3m1f Hcap Hrd",
            race_url="",
            scraped_at="2026-05-26T18:00:00Z",
            betfair_win_market_id="1.258556270",
            each_way_terms=EachWayTerms(fraction=0.2, places=3),
            runners=[
                PaddyRunner(name="Live Horse", selection_id=9,
                            win_price=7.5, win_price_raw="13/2"),
                PaddyRunner(name="Withdrawn", selection_id=7,
                            win_price=None, win_price_raw=None),
            ],
        )],
    )


class TestWritePaddypowerJson:
    def test_writes_file_with_camel_case(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        assert data["scrapedAt"] == "2026-05-26T18:00:00Z"
        assert data["raceCount"] == 1
        race = data["races"][0]
        assert race["venue"] == "Plumpton"
        assert race["country"] == "GB"
        assert race["offTime"] == "2026-05-26T18:39:00+01:00"
        assert race["marketName"] == "18:39 Plumpton - 3m1f Hcap Hrd"
        assert race["raceUrl"] == ""
        assert race["scrapedAt"] == "2026-05-26T18:00:00Z"
        assert race["betfairWinMarketId"] == "1.258556270"
        assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
        runner = race["runners"][0]
        assert runner["name"] == "Live Horse"
        assert runner["selectionId"] == 9
        assert runner["winPrice"] == 7.5
        assert runner["winPriceRaw"] == "13/2"

    def test_none_becomes_null(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        withdrawn = data["races"][0]["runners"][1]
        assert withdrawn["winPrice"] is None
        assert withdrawn["winPriceRaw"] is None

    def test_each_way_terms_can_be_null(self, tmp_path: Path):
        o = PaddyOutput(scraped_at="2026-05-26T18:00:00Z", race_count=1, races=[
            PaddyRace(venue="X", country="GB", off_time="2026-05-26T18:00:00+01:00",
                      market_name="18:00 X", race_url="", scraped_at="2026-05-26T18:00:00Z",
                      betfair_win_market_id=None, each_way_terms=None, runners=[
                          PaddyRunner(name="A", selection_id=1, win_price=None, win_price_raw=None)
                      ])])
        out = tmp_path / "paddypower.json"
        write_paddypower_json(o, out)
        data = json.loads(out.read_text())
        assert data["races"][0]["eachWayTerms"] is None
        assert data["races"][0]["betfairWinMarketId"] is None

    def test_no_tmp_file_left_behind(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        assert out.exists()
        assert not (tmp_path / "paddypower.json.tmp").exists()

    def test_empty_races(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(
            PaddyOutput(scraped_at="2026-05-26T18:00:00Z", race_count=0, races=[]),
            out,
        )
        data = json.loads(out.read_text())
        assert data == {"scrapedAt": "2026-05-26T18:00:00Z", "raceCount": 0, "races": []}

    def test_overwrites_existing(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        out.write_text('{"old": true}')
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        assert "old" not in data
        assert data["raceCount"] == 1


class TestKotlinValidatorContract:
    """Opt-in: shells out to the Kotlin PaddySchemaValidator to confirm
    Python output is byte-shape compatible with the arb finder.

    Run with: RUN_CONTRACT=1 uv run pytest -m contract"""

    pytestmark = [pytest.mark.contract]

    @pytest.mark.skipif(
        os.environ.get("RUN_CONTRACT") != "1",
        reason="set RUN_CONTRACT=1 to run cross-language contract test",
    )
    def test_sample_output_passes_kotlin_validator(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        # Repo root: tests/ is two levels under repo
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["./gradlew", "run", "--quiet",
             "-PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt",
             f"--args={out}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"validator failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
