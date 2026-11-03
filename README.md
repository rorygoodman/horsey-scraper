# Horsey Scraper

A pipeline that prices each-way arbitrage — and near-misses — between
Betfair Exchange lay prices and three bookies' win/place prices (PaddyPower,
Novibet, William Hill) for today's UK + Irish horse racing. Every fully-priced
runner gets an `edge`; the positive-edge ones are the arbs: Betfair →
PaddyPower → arb → Novibet ×2 (scrape + arb) → William Hill ×2 (scrape + arb).

1. **Betfair scrape** → `betfair.json` (multi-market lay prices via the
   Betfair Exchange REST API).
2. **PaddyPower scrape** → `paddypower.json` (win prices + each-way terms
   via a headless-Chromium fetch of PaddyPower's API).
3. **Arb finder** → `horses.json` (every fully-priced runner with its each-way edge).
4. **Novibet scrape** → `novibet.json`, then **arb finder --source novibet**
   → `novibethorses.json` (same edge, priced against Novibet; non-fatal, so a
   Novibet outage never blocks the PaddyPower publish).
5. **William Hill scrape** → `williamhill.json`, then **arb finder --source
   williamhill** → `williamhillhorses.json` (same edge, priced against William
   Hill via its public racing JSON API; also non-fatal).

888sport is no longer part of the pipeline or the site. Its scraper
(`sport888_scraper`) and `arb finder --source 888` are kept and still work
when run by hand (see below).

Pure Python. One `uv` project.

## Prerequisites

- Python ≥ 3.11 and [uv](https://github.com/astral-sh/uv).
- A Betfair account with **2FA disabled** (interactive login fails with
  `LOGIN_RESTRICTED` on 2FA-enabled accounts) and a live developer **app key**.

## One-time setup

```
brew install uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                              # creates .venv, installs deps
uv run playwright install chromium   # ~150MB; needed by the PaddyPower stage
```

## Credentials

Create `~/.horsey-scraper/credentials.json`:

```json
{
  "username": "your-betfair-username",
  "password": "your-betfair-password",
  "appKey": "your-app-key"
}
```

Recommended: `chmod 600 ~/.horsey-scraper/credentials.json`. The Betfair
stage warns to stderr if the file is readable by group/others.

## Usage

```
./run.sh               # GB + IE (default)
./run.sh us            # US only
./run.sh gb-ie,us      # both
```

Outputs are written to `./betfair.json`, `./paddypower.json`, `./horses.json`,
`./novibet.json`, `./novibethorses.json`, `./williamhill.json` and
`./williamhillhorses.json`. The Betfair and PaddyPower stages (and the first
arb-finder run) are fatal — a non-zero exit there halts the pipeline before
the PaddyPower publish. The Novibet and William Hill stages are deliberately
**non-fatal**: a failure there is logged to stderr and the pipeline
continues, so an outage in either bookie can never block the PaddyPower
publish.

Run a single stage directly:

```
uv run python -m betfair_scraper gb-ie
uv run python -m paddypower_scraper gb-ie
uv run python -m arb_finder
uv run python -m novibet_scraper gb-ie
uv run python -m williamhill_scraper gb-ie
uv run python -m arb_finder --source williamhill

# retired from run.sh, still runnable:
uv run python -m sport888_scraper gb-ie
uv run python -m arb_finder --source 888
```

## Validating output

```
uv run python -m betfair_scraper.validate betfair.json
uv run python -m paddypower_scraper.validate paddypower.json
uv run python -m arb_finder.validate horses.json
uv run python -m sport888_scraper.validate 888sport.json
uv run python -m novibet_scraper.validate novibet.json
uv run python -m williamhill_scraper.validate williamhill.json
```

## Web page (GitHub Pages)

The latest output is published as a static page at
**https://rorygoodman.github.io/horsey-scraper/** — an edge-ranked table of
every fully-priced runner (positive-edge rows highlighted). A **source**
toggle switches the table between PaddyPower (`horses.json`), Novibet
(`novibethorses.json`) and William Hill (`williamhillhorses.json`); the choice is
remembered across the page's auto-refresh.

Scrape and publish in one step:

```
./publish.sh            # GB + IE
./publish.sh us         # US only
```

`publish.sh` runs the pipeline, then force-pushes `index.html` + `horses.json`
(and `novibethorses.json` / `williamhillhorses.json` when present) to the `gh-pages`
branch (via the `gh` https credential helper). Preview the page locally
without publishing:

```
mkdir -p /tmp/horsey-preview && cp index.html /tmp/horsey-preview/
cp examples/horses.example.json /tmp/horsey-preview/horses.json
( cd /tmp/horsey-preview && python3 -m http.server 8099 )   # open http://localhost:8099
```

## Tests

```
uv run pytest                                  # unit suite
RUN_INTEGRATION=1 uv run pytest -m integration # live network/browser (opt-in)
```

## Architecture

```
src/
  common/             shared: regions, market types, ISO validation,
                      time conversion, JSON serializer
  betfair_scraper/    Betfair Exchange API scraper → betfair.json
  paddypower_scraper/ headless-Chromium PaddyPower scraper → paddypower.json
  sport888_scraper/   headless-Chromium 888sport scraper → 888sport.json
                      (retired from run.sh; kept)
  novibet_scraper/    headless-Chromium Novibet scraper → novibet.json
  williamhill_scraper/ William Hill racing-API scraper (plain HTTPS) →
                      williamhill.json
  arb_finder/         joins betfair.json with one bookie's scrape →
                      horses.json / 888horses.json / novibethorses.json /
                      williamhillhorses.json
```

Design docs live under `docs/superpowers/specs/`, implementation plans
under `docs/superpowers/plans/`.
