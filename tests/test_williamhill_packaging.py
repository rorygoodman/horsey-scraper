import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_includes_williamhill_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/williamhill_scraper" in pkgs


def test_script_entry_present():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["williamhill-scraper"] == \
        "williamhill_scraper.cli:main"


def test_run_sh_invokes_williamhill_stages():
    text = (ROOT / "run.sh").read_text()
    assert "python -m williamhill_scraper" in text
    assert "python -m arb_finder --source williamhill" in text


def test_run_sh_williamhill_stages_are_non_fatal():
    # A William Hill outage must never abort run.sh and block the PaddyPower publish.
    text = (ROOT / "run.sh").read_text()
    stage_lines = [
        l for l in text.splitlines()
        if "williamhill_scraper" in l or "--source williamhill" in l
    ]
    assert len(stage_lines) == 2, f"expected 2 williamhill stage lines, got {stage_lines}"
    for line in stage_lines:
        assert "||" in line, f"williamhill stage must be non-fatal: {line!r}"


def test_gitignore_lists_williamhill_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "williamhill.json" in text
    assert "williamhillhorses.json" in text
