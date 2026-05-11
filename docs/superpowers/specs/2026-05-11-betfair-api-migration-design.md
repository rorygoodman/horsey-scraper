---
status: draft
date: 2026-05-11
topic: Replace Selenium scraping with the Betfair Exchange API
---

# Replace Selenium scraping with the Betfair Exchange API

## Goal

Replace every Selenium/Chrome scraping path in this repo with calls to the
Betfair Exchange REST API. Output (`data.json`) keeps its current schema and
passes the existing `SchemaValidator` byte-for-byte. The result is a runtime
that finishes in seconds, has no Chrome dependency, and reads the same
authoritative data that the Betfair UI shows.

## Non-goals

- No change to the output schema. Existing `data.json` consumers (humans, the
  validator, any future code) continue to work.
- No change to which markets we capture. Still `WIN` plus the explicit
  `Top 2 / 3 / 4 / 5 Finish` markets, *not* the regular "To Be Placed" market.
- No streaming-API support. We use the REST endpoints only.
- No cert-based (non-interactive) login. Interactive login only; cert-based
  login is a possible future extension.
- No automatic retries, no rate-limit backoff. If a call fails we fall back to
  the existing per-market / per-race omission rules.
- No persistence of the ssoid across runs. Each run logs in fresh.

## Prerequisites

- A Betfair account with 2FA **disabled**. Interactive login (the only auth
  flow this design supports) returns `LOGIN_RESTRICTED` for 2FA-enabled
  accounts. The spec calls this out explicitly so the failure mode is
  debuggable; the error message on login will reference this requirement.
- A Betfair developer app key (live, not delayed).
- A credentials file at `~/.horsey-scraper/credentials.json` (see below).

## Approach

**Surgical replacement.** Keep the existing module boundaries that the
validator depends on (`Models.kt`, `RunnerPivot.kt`, `SchemaValidator.kt`,
`OffTimeBuilder.kt`, `RaceIdParser.kt`, `Main.kt`'s shape). Rewrite the two
scraper types (`BetfairRaceListScraper`, `BetfairRaceScraper`) into API-backed
fetchers, delete every Selenium-specific file, and drop the worker pool /
debug entry points that were tied to the browser implementation.

Hand-rolled HTTP via `java.net.http.HttpClient` + Gson. No third-party Betfair
library. The API surface we need is small (login + two betting endpoints).

## Module layout

### New files (under `src/main/kotlin/com/horsey/scraper/`)

- **`BetfairClient.kt`** — auth + HTTP transport. Single class wrapping
  `java.net.http.HttpClient` and Gson. Methods:
  - `login()` — POST to `https://identitysso.betfair.com/api/login`; returns
    ssoid on success; throws on non-`SUCCESS` status.
  - `listMarketCatalogue(filter, projection, maxResults, sort)` — POST to
    `https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/`.
  - `listMarketBook(marketIds, priceProjection)` — POST to
    `https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/`.
    Caller is responsible for batching to ≤40 IDs per call.

  Holds ssoid + appKey as instance fields, injects `X-Application` and
  `X-Authentication` headers automatically.

- **`Credentials.kt`** — reads `~/.horsey-scraper/credentials.json`. Splits
  into a pure parser (`parseCredentials(json: String): Credentials`) and an
  IO wrapper that handles file-not-found, mode check, and JSON read. The pure
  parser is unit-tested directly.

- **`Regions.kt`** — replaces the deleted `Venues.kt`. Tiny lookup table:
  `gb-ie` → `["GB", "IE"]`, `us` → `["US"]`. Used by `parseRegions` and by
  `RaceListFetcher` to build the API filter.

- **`RaceListFetcher.kt`** — replaces `BetfairRaceListScraper`. One method,
  `fetch(regions: Set<String>): List<Race>`. Calls `listMarketCatalogue`
  once per *country group* (one call per region selected — typically one or
  two calls total) and builds a `Race` per returned WIN market.

- **`RaceOddsFetcher.kt`** — replaces `BetfairRaceScraper`. One method,
  `fetch(races: List<Race>): List<RaceOdds>`. Calls
  `listMarketCatalogue` once for the PLACE markets across all the races'
  events (one call total), classifies them via `MarketClassifier`, then
  fetches all prices via `listMarketBook` batched to ≤40 IDs.

- **`MarketClassifier.kt`** — pure function:

  ```kotlin
  fun classifyMarket(name: String, numberOfWinners: Int): MarketType?
  ```

  Returns `TOP_2`/`TOP_3`/`TOP_4`/`TOP_5` when `name` matches
  `^Top [2-5] Finish$` (case-insensitive) **and** `numberOfWinners` matches
  the N. Returns `null` for the regular "To Be Placed" market and anything
  else. This is the same filter the old `RelatedMarketsFinder` applied to
  DOM text.

### Files kept verbatim

`Models.kt`, `RunnerPivot.kt`, `OffTimeBuilder.kt`, `RaceIdParser.kt`,
`SchemaValidator.kt`, `ValidateMain.kt`, and the corresponding tests
(`RunnerPivotTest`, `OffTimeBuilderTest`, `MarketTypeTest`,
`SchemaValidatorTest`, `RaceIdParserTest`, `ModelsJsonTest`, `SanityTest`).

### Files deleted

`BetfairRaceListScraper.kt`, `BetfairRaceScraper.kt`, `MarketScraper.kt`,
`RelatedMarketsFinder.kt`, `WebDriverUtils.kt`, `RaceWorkerPool.kt`,
`Venues.kt`, `DebugListMain.kt`, `DebugMarketLinks.kt`, `DebugMarketName.kt`,
`TestListMain.kt`, `TestRaceMain.kt`,
`BetfairRaceListScraperTest.kt`, `BetfairRaceScraperAssemblyTest.kt`,
`RaceWorkerPoolTest.kt`, and the repo-root `debug-page.html`.

### `Main.kt` (rewritten)

```text
parse CLI (regions only)
  → load credentials
  → BetfairClient(appKey).login(username, password)
  → RaceListFetcher(client).fetch(regions)
  → RaceOddsFetcher(client).fetch(races)
  → write data.json
```

Top-level `scrapedAt` is `Instant.now()` at run start. Per-market
`marketScrapedAt[type]` is `Instant.now()` at the moment that market's
`listMarketBook` response is received.

### `build.gradle.kts`

Drop `org.seleniumhq.selenium:selenium-java` and
`org.slf4j:slf4j-simple`. Keep `com.google.code.gson:gson`. No new
dependencies.

## API mapping

### Authentication

```
POST https://identitysso.betfair.com/api/login
Headers: X-Application: <appKey>, Accept: application/json
Body (form): username=<user>&password=<pass>
```

Response: `{"token": "<ssoid>", "status": "SUCCESS", ...}`. Non-`SUCCESS`
status (e.g. `LOGIN_RESTRICTED`, `INVALID_USERNAME_OR_PASSWORD`) → exit 1
with the status code in the message. Any error message for
`LOGIN_RESTRICTED` includes "this likely means 2FA is enabled on the
account; 2FA must be disabled for interactive login to work, or switch to
cert-based login."

The returned ssoid is sent on every subsequent call as
`X-Authentication: <ssoid>`.

### Race list

One `listMarketCatalogue` call total, with `marketCountries` set to the
union of the country codes of all selected regions (e.g. selecting both
`gb-ie` and `us` produces `["GB", "IE", "US"]`).

```
POST https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/
Headers: X-Application, X-Authentication, Content-Type: application/json
Body:
{
  "filter": {
    "eventTypeIds": ["7"],
    "marketCountries": ["GB", "IE"],
    "marketTypeCodes": ["WIN"],
    "marketStartTime": {
      "from": "<today 00:00 Europe/London → UTC>",
      "to":   "<tomorrow 00:00 Europe/London → UTC>"
    }
  },
  "marketProjection": ["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
  "maxResults": "1000",
  "sort": "FIRST_TO_START"
}
```

Per returned market, build a `Race`:

| `Race` field | API source |
|---|---|
| `raceId` | `marketId` (already in `1.NNN` form) |
| `venue` | `event.venue` |
| `country` | `event.countryCode` |
| `offTime` | `marketStartTime` (UTC), converted to Europe/London offset |
| `winMarketUrl` | Constructed: `"https://www.betfair.com/exchange/plus/horse-racing/market/<marketId>"` |

`marketName` (per-race output field) is built from `OffsetDateTime`(offTime,
HH:mm) + `event.venue` + the API `marketName` from the WIN market (e.g.
`"5f Hcap"`), producing the existing `"<HH:mm> <venue> - <race type>"`
format. If the API `marketName` is empty, the `" - <race type>"` suffix is
omitted (same fallback as today).

### Top-N markets

One additional `listMarketCatalogue` call for all PLACE markets in scope:

```json
{
  "filter": {
    "eventTypeIds": ["7"],
    "marketCountries": ["GB", "IE"],
    "marketTypeCodes": ["PLACE"],
    "marketStartTime": { "from": "...", "to": "..." }
  },
  "marketProjection": ["EVENT", "MARKET_DESCRIPTION"],
  "maxResults": "1000"
}
```

Each PLACE result is classified by `MarketClassifier` using its
`marketName` and `description.numberOfWinners`. Markets that don't match
the `^Top [2-5] Finish$` pattern (e.g. the standard "To Be Placed" market)
are silently ignored. Classified markets are joined back to the matching
`Race` by `event.id` and their `MarketType` is recorded.

### Prices

Collect every marketId in scope (WIN + classified TOP_N), chunk into groups
of 40, and call `listMarketBook` per chunk:

```json
{
  "marketIds": ["1.249...", "1.249...", ...],
  "priceProjection": { "priceData": ["EX_BEST_OFFERS"] }
}
```

Per `MarketBook` in the response:

- If `status != "OPEN"` (e.g. `SUSPENDED`, `CLOSED`) → treat as a failed
  scrape: key omitted from `marketScrapedAt` and from every runner's `lay`.
- Otherwise: for each `runner`, best lay =
  `runner.ex.availableToLay[0].price` or `null` if the array is empty.

Runner names are sourced from each market's `runners[].runnerName` in the
catalogue response, joined to the `MarketBook` by `selectionId`.

Phantom horses (selectionId present in a Top-N `MarketBook` but not in the
WIN market for the same race) are dropped with the existing stderr warning
emitted by `pivotMarketScrapes` — no change to that logic.

### Edge-case rules (unchanged)

All eight rules from the multi-market spec
(`2026-05-09-multi-market-lay-schema-design.md`) carry over verbatim. Key
presence/absence parity between `marketScrapedAt` and each runner's `lay`
is enforced by `SchemaValidator`, which is unchanged.

## Operational concerns

### Credentials file

Path: `~/.horsey-scraper/credentials.json`. Shape:

```json
{
  "username": "...",
  "password": "...",
  "appKey": "..."
}
```

- File missing → exit 2 with a message naming the expected path.
- Malformed JSON or missing fields → exit 2, listing the bad fields.
- File mode is not `0600` → warning to stderr, continue.

Repo `.gitignore` gets defensive entries for `credentials.json` and
`*.env` even though the file lives outside the repo.

### CLI

Single positional arg: `regions` (comma-separated, case-insensitive).
Default `gb-ie`. Valid IDs come from the new `Regions.kt`. Unknown IDs →
exit 1 with a message listing the valid set.

`run.sh` simplifies to:

```bash
#!/usr/bin/env bash
exec ./gradlew run --quiet --args="${1:-gb-ie}"
```

### Errors and exits

| Situation | Behaviour |
|---|---|
| Credentials missing / malformed | exit 2, naming the issue |
| Invalid CLI args | exit 1, listing valid options |
| Login fails | exit 1, printing the Betfair status code |
| Network/HTTP error on race-list `listMarketCatalogue` | exit 1 — no races, nothing to write |
| Per-market `listMarketBook` error | drop affected market(s); WIN drop ⇒ drop race |
| Successful run with zero races | write a valid `data.json` with `raceCount: 0` |

### Documentation

A short `README.md` at repo root documents prerequisites (Betfair account,
2FA off, app key), credentials file path/shape, and CLI usage. Existing
specs and plans under `docs/superpowers/` are unchanged.

## Testing

The validator and pivot tests are the existing safety net and stay
unchanged. New unit tests are all pure (no live API, no HTTP):

- **`CredentialsTest`** — parser happy path; missing fields; malformed
  JSON; extra fields ignored.
- **`MarketClassifierTest`** — `Top N Finish` names with matching
  `numberOfWinners` classify correctly; mismatched numbers reject; "To Be
  Placed" rejects; arbitrary other names reject.
- **`RaceFromCatalogueTest`** — given a canned `MarketCatalogue` JSON
  blob, `Race` fields are built correctly; UTC→Europe/London conversion
  produces the expected offset; `winMarketUrl` is the right format.
- **`LayPriceExtractorTest`** — given canned `MarketBook` JSON, lay
  extraction is correct; empty `availableToLay` → `null`; `status =
  SUSPENDED` → market dropped.
- **`ParseRegionsTest`** — the existing single-arg parser parses correctly
  in its new position (`args[0]`); default behaviour when no args;
  unknown region errors. (The existing parser logic is unchanged; the
  test verifies the new index.)

Removed: `BetfairRaceListScraperTest`, `BetfairRaceScraperAssemblyTest`,
`RaceWorkerPoolTest`.

End-to-end verification is a manual smoke run followed by `./gradlew run
-PmainClass=com.horsey.scraper.ValidateMainKt --args=data.json` to confirm
the output passes schema validation.

## Acceptance

A run with valid credentials completes within ~10 seconds (typical day,
~50-200 horse-racing markets across GB+IE) and produces a `data.json` such
that:

- Top-level shape matches the existing schema.
- `SchemaValidator` reports zero errors.
- For at least one race, `marketScrapedAt` contains all five keys (`WIN`,
  `TOP_2`, `TOP_3`, `TOP_4`, `TOP_5`).
- For a race where some Top-N markets don't exist on Betfair,
  `marketScrapedAt` and each runner's `lay` map contain only the keys
  that were successfully fetched.
- No Selenium classes are referenced anywhere in the codebase
  (`grep -r selenium src/` returns nothing).
- `gradle dependencies` lists no `org.seleniumhq.selenium:*` artefact.
- A phantom horse (selectionId in a Top-N MarketBook but not WIN) produces
  the existing `Phantom horse '<name>' in <market> for race <raceId> —
  dropping` stderr warning.

## Migration

This is a behavioural rewrite, not a schema change. There are no
documented downstream consumers of `data.json` other than this repo's own
`SchemaValidator`. Old `data.json` files are overwritten at next run.

## Open implementation questions

These are not blocking on the design and will be resolved at plan time:

- **Exact API base URL by jurisdiction.** Betfair has multiple endpoints
  (UK/Italy/Spain). For GB/IE/US horse racing the standard `api.betfair.com`
  endpoint is correct, but verify on first live call.
- **Time-window precision.** Whether `marketStartTime.from/to` should be
  exactly midnight London-local or shift slightly to catch boundary races.
  Default to midnight London; revisit if a race is missed.
- **Empty fields in the API.** Whether any of `event.venue`,
  `event.countryCode`, `description.numberOfWinners` can be missing in
  practice for horse-racing markets. If so, decide drop-vs-warn at plan
  time.
