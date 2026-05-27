#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: Betfair scrape → PaddyPower scrape → arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
REGIONS="${1:-gb-ie}"
uv run python -m betfair_scraper "$REGIONS"
uv run python -m paddypower_scraper "$REGIONS"
exec uv run python -m arb_finder
