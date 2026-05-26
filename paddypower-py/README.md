# paddypower-py

Python scraper for PaddyPower racing. Produces `paddypower.json` at the
repo root, consumed by the Kotlin arb finder.

## One-time setup

```bash
# Install uv (macOS) or via install script (Linux/WSL)
brew install uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync --project paddypower-py
uv run --project paddypower-py playwright install chromium
```

## Run manually

```bash
uv --project paddypower-py run python -m paddypower_scraper gb-ie
```

Valid regions: `gb-ie`, `us`, or any comma-separated combination
(e.g. `gb-ie,us`). Default: `gb-ie`.

## Test

```bash
uv --project paddypower-py run pytest                              # unit tests
RUN_INTEGRATION=1 uv --project paddypower-py run pytest -m integration   # real Chromium
RUN_CONTRACT=1 uv --project paddypower-py run pytest -m contract         # Kotlin schema validator
```

## Design

See `docs/superpowers/specs/2026-05-26-paddypower-python-scraper-design.md`.
