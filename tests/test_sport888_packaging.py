import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_includes_sport888_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/sport888_scraper" in pkgs


def test_script_entry_present():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["sport888-scraper"] == "sport888_scraper.cli:main"


def test_run_sh_invokes_888_stages():
    text = (ROOT / "run.sh").read_text()
    assert "python -m sport888_scraper" in text
    assert "python -m arb_finder --source 888" in text


def test_gitignore_lists_888_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "888sport.json" in text
    assert "888horses.json" in text
