#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: Betfair scrape → PaddyPower scrape → arb finder → 888 scrape →
# 888 arb finder → Novibet scrape → Novibet arb finder.
# The Betfair/PaddyPower stages are fatal (a failure exits non-zero, so publish
# is skipped rather than shipping stale prices). The 888 and Novibet stages are
# non-fatal (`|| …`): an outage in either must never block the PaddyPower
# publish, and their horses files are only published when present.
set -euo pipefail
REGIONS="${1:-gb-ie}"
uv run python -m betfair_scraper "$REGIONS"
uv run python -m paddypower_scraper "$REGIONS"
uv run python -m arb_finder
uv run python -m sport888_scraper "$REGIONS" || echo "run.sh: 888 scrape failed (exit $?); PaddyPower publish unaffected" >&2
uv run python -m arb_finder --source 888 || echo "run.sh: 888 arb failed (exit $?); PaddyPower publish unaffected" >&2
uv run python -m novibet_scraper "$REGIONS" || echo "run.sh: novibet scrape failed (exit $?); PaddyPower publish unaffected" >&2
uv run python -m arb_finder --source novibet || echo "run.sh: novibet arb failed (exit $?); PaddyPower publish unaffected" >&2
