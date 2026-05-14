#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: scrapers (Betfair + PaddyPower) → arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
./gradlew run --quiet --args="${1:-gb-ie}"
exec ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt
