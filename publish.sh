#!/usr/bin/env bash
# Scrape today's racing and publish horses.json + index.html to GitHub Pages.
# Usage: ./publish.sh [regions]   (default gb-ie; passed through to run.sh)
#
# Force-pushes a throwaway public/ tree to the gh-pages branch of `origin`
# (authenticated by the gh https credential helper). Run after `gh` login.
set -euo pipefail
cd "$(dirname "$0")"
REGIONS="${1:-gb-ie}"

# 1. Scrape → horses.json at repo root. Aborts (set -e) if the scrape fails.
./run.sh "$REGIONS"

# 2. Stage the site.
rm -rf public
mkdir -p public
cp index.html horses.json public/

# 3. Force-push public/ as the gh-pages branch.
ORIGIN_URL="$(git remote get-url origin)"
cd public
git init -q
git checkout -q -B gh-pages
git add -A
git commit -q -m "Publish $(date -u '+%Y-%m-%dT%H:%MZ')"
git push -fq "$ORIGIN_URL" gh-pages

echo "Published → https://rorygoodman.github.io/horsey-scraper/"
