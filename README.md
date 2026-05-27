# Horsey Scraper

A three-stage pipeline that prices each-way arbitrage — and near-misses —
between PaddyPower win/place prices and Betfair Exchange lay prices for
today's UK + Irish horse racing. Every fully-priced runner gets an `edge`;
the positive-edge ones are the arbs:

1. **Betfair scrape** → `betfair.json` (multi-market lay prices via the
   Betfair Exchange REST API).
2. **PaddyPower scrape** → `paddypower.json` (win prices + each-way terms
   via a headless-Chromium fetch of PaddyPower's API).
3. **Arb finder** → `horses.json` (every fully-priced runner with its each-way edge).

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

Outputs are written to `./betfair.json`, `./paddypower.json`, `./horses.json`.
A non-zero exit at any stage halts the pipeline before the edge step.

Run a single stage directly:

```
uv run python -m betfair_scraper gb-ie
uv run python -m paddypower_scraper gb-ie
uv run python -m arb_finder
```

## Validating output

```
uv run python -m betfair_scraper.validate betfair.json
uv run python -m paddypower_scraper.validate paddypower.json
uv run python -m arb_finder.validate horses.json
```

## Web page (GitHub Pages)

The latest output is published as a static page at
**https://rorygoodman.github.io/horsey-scraper/** — an edge-ranked table of
every fully-priced runner (positive-edge rows highlighted).

Scrape and publish in one step:

```
./publish.sh            # GB + IE
./publish.sh us         # US only
```

`publish.sh` runs the pipeline, then force-pushes `index.html` + `horses.json`
to the `gh-pages` branch (via the `gh` https credential helper). Preview the
page locally without publishing:

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
  arb_finder/         joins both files → horses.json
```

Design docs live under `docs/superpowers/specs/`, implementation plans
under `docs/superpowers/plans/`.
