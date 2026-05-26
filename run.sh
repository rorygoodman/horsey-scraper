#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: Kotlin Betfair scrape → Python PaddyPower scrape → Kotlin arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
REGIONS="${1:-gb-ie}"
./gradlew run --quiet --args="$REGIONS"
uv --project paddypower-py run python -m paddypower_scraper "$REGIONS"
exec ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt
