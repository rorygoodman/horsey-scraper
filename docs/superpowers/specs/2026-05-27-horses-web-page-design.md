---
status: draft
date: 2026-05-27
topic: Static GitHub Pages page that displays horses.json
---

# horses.json web page (GitHub Pages)

## Goal

A static, self-contained HTML page that displays the latest `horses.json`
as a table ranked by edge (best first), published to GitHub Pages — so the
scraper's output is viewable in a browser. (v1 has filters but no
clickable column sorting — the rows are pre-sorted by edge.) Modelled on the existing `golf-odds-scraper`
pattern (`index.html` + a data file on a `gh-pages` branch, pushed by a
`publish.sh`).

## Motivation

`horses.json` is a local, gitignored output; today the only way to read it
is on the command line. A simple hosted page makes the per-runner edges
glanceable — best opportunities at the top, positive edges highlighted —
and matches how the golf scraper already surfaces its data.

## Non-goals

- **No build step / framework.** One self-contained `index.html` (inline
  CSS + vanilla JS, no external dependencies). No React, no bundler.
- **No CI.** Publishing is a manual/cron `publish.sh`, exactly like the
  golf scraper. The Betfair-credentialed scrape is not run in CI.
- **No server / API.** Static files only; the page fetches `horses.json`
  client-side.
- **Not the richer golf feature set** (clickable column sort, localStorage
  "seen" tracking, tabs, per-brand themes). v1 is a single sortable table.
- **No change to the scraper, the pipeline, or the `horses.json` schema.**
  The page is a pure consumer of the existing output.

## Architecture & data flow

Two new files at the repo root plus a generated `gh-pages` branch:

```
./publish.sh [regions]
   1. ./run.sh [regions]                # betfair → paddypower → horses.json (repo root)
   2. rm -rf public && mkdir public
      cp index.html horses.json public/
   3. cd public/ ; git init ; git checkout -B gh-pages
      git add -A ; git commit ; git push -f <origin-url> gh-pages
GitHub Pages (gh-pages branch, root) → https://rorygoodman.github.io/horsey-scraper/
   index.html  → fetch('horses.json') → render table
```

- `public/` is a throwaway one-commit git repo force-pushed to `gh-pages`
  (the golf trick; `gh-pages` history is disposable). It pushes to the
  existing **https `origin`** (resolved with `git remote get-url origin`),
  authenticated by the `gh` credential helper already configured — no SSH
  key (the one deviation from golf, which used SSH for cron).
- `public/` and `horses.json` are gitignored on `master`; they live only
  on `gh-pages`.
- **One-time setup:** after the first publish creates `gh-pages`, enable
  Pages with source = `gh-pages` branch, path `/` (via `gh api`).

## Components

### `index.html` (the page)

One self-contained file: inline `<style>` (dark theme, consistent with the
golf page's look) and inline `<script>` (vanilla JS, no deps).
`<meta http-equiv="refresh" content="600">` auto-refreshes every 10 minutes.

On load it `fetch('horses.json')` (relative path) and renders:

- **Header:** an `<h1>` title and a summary line:
  `updated <computedAt rendered in local time> · <N> horses · <M> with edge>0`.
- **Controls:**
  - a venue `<select>` populated from the distinct `horses[].venue` values
    (plus an "All venues" default);
  - an "edge > 0 only" checkbox.
- **Table**, default order = the data's own order (already sorted by `edge`
  descending). Columns, left→right:

  | column | source | format |
  |---|---|---|
  | edge | `edge` | percent, 2 dp, signed (e.g. `+4.69%`); green text when `> 0` |
  | time | `offTime` | `HH:mm` (from the ISO offset string) |
  | venue | `venue` | text |
  | runner | `runner.name` | text |
  | PP | `paddypower.winPrice` (+ `winPriceRaw`) | price, raw shown as a hint e.g. `15.0 (15/8)` |
  | BF win | `betfair.winLay` | price |
  | place | `betfair.placeMarket` | the TOP_N name (e.g. `TOP_3`) |
  | plc | `betfair.placeLay` | price |

  Rows with `edge > 0` get a green row highlight.

- **Filtering:** the venue `<select>` and "edge > 0 only" checkbox filter
  the visible rows client-side and update the summary counts. (`N`/`M` in
  the summary always reflect the full dataset, not the filtered view.)
- **States:**
  - `horseCount: 0` (or empty `horses`) → a message "No fully-priced
    runners right now." instead of an empty table.
  - `fetch` failure (missing/unreachable `horses.json`) → a clear error
    message, not a blank page.

The page reads only fields the `horses.json` schema guarantees:
`computedAt`, `horseCount`, and per horse `offTime`, `venue`,
`runner.name`, `paddypower.winPrice`, `paddypower.winPriceRaw`,
`betfair.winLay`, `betfair.placeLay`, `betfair.placeMarket`, `edge`.

### `publish.sh` (the publisher)

```bash
#!/usr/bin/env bash
# Scrape today's racing and publish horses.json + index.html to GitHub Pages.
# Usage: ./publish.sh [regions]   (default gb-ie; passed through to run.sh)
set -euo pipefail
cd "$(dirname "$0")"
REGIONS="${1:-gb-ie}"

./run.sh "$REGIONS"                     # → horses.json (aborts here on scrape failure)

rm -rf public && mkdir -p public
cp index.html horses.json public/

ORIGIN_URL="$(git remote get-url origin)"
cd public
git init -q && git checkout -q -B gh-pages
git add -A && git commit -q -m "Publish $(date -u '+%Y-%m-%dT%H:%MZ')"
git push -fq "$ORIGIN_URL" gh-pages
echo "Published → https://rorygoodman.github.io/horsey-scraper/"
```

- `set -euo pipefail`: a scrape failure (non-zero `run.sh`) aborts before
  publishing. A legitimate 0-horse day (`run.sh` exits 0) still publishes
  an empty `horses.json`, and the page shows the empty state.
- `public/` is wiped and rebuilt each run; its throwaway `.git` force-pushes
  a fresh single commit to `gh-pages`.
- Commit identity comes from the global git config (already set).

### `examples/horses.example.json`

A small committed sample (a few horses, including one positive-edge row and
one negative) matching the `horses.json` schema. Purpose: offline preview of
the page, and living documentation of the shape the page consumes. Kept
valid by a test (below).

### Repo changes

- `.gitignore`: add `public/` (`horses.json` already ignored).
- `README.md`: a "Web page" section — the Pages URL and `./publish.sh
  [regions]` to update it (noting it force-pushes `gh-pages`).

## Testing & verification

A static HTML page + bash script don't fit unit tests; verification is
mostly visual, backed by a thin automated guard.

### Automated — `tests/test_site.py`
- **Example validates:** `examples/horses.example.json` passes
  `arb_finder.validation.validate_horses_output` (returns `[]`). This stops
  the preview sample from drifting away from the real schema.
- **Page ↔ schema hooks:** `index.html` contains `horses.json` and each
  field name the page depends on: `edge`, `winLay`, `placeLay`,
  `placeMarket`, `winPrice`, `computedAt`, `horseCount`. Catches the page
  silently breaking if it references a field the schema doesn't produce.

These run under the existing `uv run pytest` and must keep the suite green.

### Manual — local visual preview
Serve over HTTP (browsers block `fetch` on `file://`):
```
mkdir -p /tmp/horsey-preview
cp index.html /tmp/horsey-preview/
cp examples/horses.example.json /tmp/horsey-preview/horses.json
( cd /tmp/horsey-preview && python3 -m http.server 8000 )
# open http://localhost:8000
```
Confirm: table renders; positive edge is green; venue filter works;
"edge > 0 only" toggles; the summary counts are right. Then point at an
empty `horses.json` (`{"computedAt":"…","horseCount":0,"horses":[]}`) to
confirm the empty state, and remove the file to confirm the error state.

### End-to-end
One real `./publish.sh` (during racing hours, with credentials) → check the
live Pages URL renders the day's data. This run also first creates the
`gh-pages` branch; enable Pages once afterwards.

## Risks

- **Push auth.** `publish.sh` relies on the `gh` https credential helper
  being configured for `origin` (it is, from `gh repo create`). On a
  machine without it, the push would prompt/fail; documented in the README.
- **Public data.** The repo is public, so `gh-pages` (and the published
  `horses.json`) are world-readable. The data is odds/edges only — no
  credentials — consistent with the golf scraper already being public.
- **Field drift.** If the `horses.json` schema field names ever change, the
  page breaks silently; the `test_site.py` hook check is the guard.
