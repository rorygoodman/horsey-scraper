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


def test_run_sh_no_longer_runs_888_stages():
    # 888sport is retired from the pipeline; the package stays importable and
    # `arb_finder --source 888` still works by hand.
    text = (ROOT / "run.sh").read_text()
    stage_lines = [
        l for l in text.splitlines()
        if l.startswith("uv run")
        and ("sport888_scraper" in l or "--source 888" in l)
    ]
    assert stage_lines == []


def test_gitignore_lists_888_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "888sport.json" in text
    assert "888horses.json" in text
