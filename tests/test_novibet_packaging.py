import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_includes_novibet_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/novibet_scraper" in pkgs


def test_script_entry_present():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["novibet-scraper"] == "novibet_scraper.cli:main"


def test_run_sh_invokes_novibet_stages():
    text = (ROOT / "run.sh").read_text()
    assert "python -m novibet_scraper" in text
    assert "python -m arb_finder --source novibet" in text


def test_run_sh_novibet_stages_are_non_fatal():
    # A Novibet outage must never abort run.sh and block the PaddyPower publish.
    text = (ROOT / "run.sh").read_text()
    stage_lines = [
        l for l in text.splitlines()
        if "novibet_scraper" in l or "--source novibet" in l
    ]
    assert len(stage_lines) == 2, f"expected 2 novibet stage lines, got {stage_lines}"
    for line in stage_lines:
        assert "||" in line, f"novibet stage must be non-fatal: {line!r}"


def test_gitignore_lists_novibet_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "novibet.json" in text
    assert "novibethorses.json" in text
