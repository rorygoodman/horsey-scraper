# Horsey Scraper

One-shot CLI that fetches today's UK + Irish horse-racing lay-side prices
from the Betfair Exchange API and writes them to `data.json`.

## Prerequisites

- A Betfair account with **2FA disabled**. Interactive login fails
  (`LOGIN_RESTRICTED`) on 2FA-enabled accounts.
- A Betfair developer **app key** (live, not delayed).
- JDK 17.

## Credentials

Create `~/.horsey-scraper/credentials.json`:

```json
{
  "username": "your-betfair-username",
  "password": "your-betfair-password",
  "appKey": "your-app-key"
}
```

Recommended: `chmod 600 ~/.horsey-scraper/credentials.json`. The scraper
warns to stderr if the file is readable by group/others.

## Usage

```
./run.sh               # GB + IE (default)
./run.sh us            # US only
./run.sh gb-ie,us      # both
```

Output is written to `./data.json`. Schema is documented in
`docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md`.

## Validating output

```
./gradlew run --quiet -PmainClass=com.horsey.scraper.ValidateMainKt --args=data.json
```

## Architecture

- `BetfairClient` — login + two betting endpoints (catalogue, book).
- `RaceListFetcher` — today's WIN markets in selected regions.
- `RaceOddsFetcher` — PLACE markets classified as Top-N + batched prices.
- `RunnerPivot` (unchanged) — flips per-market lay maps to per-runner.
- `SchemaValidator` (unchanged) — enforces the output contract.

Design docs live under `docs/superpowers/specs/` and implementation plans
under `docs/superpowers/plans/`.
