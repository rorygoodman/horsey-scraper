---
status: draft
date: 2026-05-14
topic: PaddyPower US racing — extend the next-races scraper to a second region
---

# PaddyPower US racing scraper

## Goal

Extend the existing PaddyPower next-races scraper so it also captures
PaddyPower's daily US horse-racing markets. A single `./run.sh
gb-ie,us` invocation should produce a `paddypower.json` containing both
GB/IE and US races, feeding the arb finder so US-side arbitrage
opportunities surface alongside the existing GB/IE ones.

## Non-goals

- No new bookmaker. PaddyPower is still the only back-side source.
- No change to the `paddypower.json` JSON schema. The new races just
  appear in `races[]` with `country: "US"`. The existing
  `PaddySchemaValidator` and downstream consumers (arb finder, future
  static site) are untouched.
- No parallel Playwright launches. The two URL fetches happen
  sequentially. Adds ~10s to a `./run.sh` invocation. Acceptable for a
  one-shot CLI.
- No retry on a failed URL fetch. The user re-runs.
- No browser-instance reuse between the two URL fetches. Each launches
  its own short-lived Chromium (existing pattern).
- No region-specific `cardsToFetch` parameterisation beyond the two
  URLs. If PaddyPower adds new card types later, they're a separate
  spec.
- No partial-region CLI tricks. The `regions` arg only controls the
  *output filter*; both URLs are always fetched.

## Prerequisites

- Existing `paddypower.json` pipeline (one URL, GB/IE) working — done
  in the PaddyPower scraper project (commit `121971c` onwards).
- Playwright + Chromium binary installed (`./gradlew run --quiet
  -PmainClass=com.microsoft.playwright.CLI --args="install chromium"`)
  — same prerequisite as the existing pipeline.
- A second DevTools-captured URL: PaddyPower's content-managed-page
  endpoint targeting US racing. Captured by the user during the plan's
  Task 0, same procedure as the original PaddyPower work.

## Approach

**Region-symmetric client.** `PaddyClient` is extended to fetch two
URLs (GB/IE + US) on every call, returning a `List<String>` of JSON
response bodies. `PaddyNextRacesFetcher` parses each independently and
concatenates the `PaddyRace` results before applying the existing
region filter. No new JSON shape, no schema-validator change, no new
domain types.

The PaddyPower JSON shape is the same on both URLs (verified
upfront — both come from the same `apisms.paddypower.com/smspp/content-managed-page/v7`
endpoint with a different `cardsToFetch=…` value or other minor query
param). If implementation reveals a structurally different shape on the
US URL, that's a hard escalation — the spec doesn't accommodate it.

## Module changes

### `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`

- Rename the existing `NEXT_RACES_URL` constant to
  `NEXT_RACES_URL_GBIE`.
- Add a new constant `NEXT_RACES_URL_US` populated by Task 0 of the
  plan (DevTools capture).
- Change `getNextRaces(): String` → `getNextRaces(): List<String>`.
- Implementation: iterate `listOf(NEXT_RACES_URL_GBIE,
  NEXT_RACES_URL_US)`. For each URL, run the existing Playwright +
  in-page `fetch()` flow under its own short-lived browser lifecycle.
  Each URL gets a separate try/catch.
- Per-URL failure: print
  `"paddy: failed to fetch <URL>: <error message>"` to stderr; skip
  that URL.
- After both attempts: if the result list is empty (both URLs failed),
  throw `IllegalStateException("PaddyClient: every configured URL
  failed")`. Otherwise return the non-empty list.

### `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`

- `fetch()` now consumes a `List<String>` from the client. For each
  response body, call the existing
  `parsePaddyNextRaces(jsonBody, nowProvider)` (unchanged signature).
  Concatenate the resulting `List<PaddyRace>` lists in client-return
  order.
- Apply the existing `filterRacesByCountries` to the concatenated list.
- Top-level `scrapedAt` is still captured once, at the start of
  `fetch()`, before the client call (same as today).

### `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`

- **No changes.** The US response has the same JSON shape; existing
  parser, helpers, and edge-case rules apply uniformly.

### Fixture files

- Existing: `src/test/resources/paddy-next-races-sample.json` (GB/IE)
  and `paddy-next-races-endpoint.txt`. Unchanged.
- New: `src/test/resources/paddy-next-races-us-sample.json` (US
  response) and `paddy-next-races-us-endpoint.txt` (URL + metadata).
  Both captured during the plan's Task 0.

### `run.sh` and `.gitignore`

- **No changes.** The existing `./run.sh` already accepts the regions
  arg; the same arg flows through to the existing
  `PaddyNextRacesFetcher.fetch(regions)`. Output filename is unchanged.

## Failure handling

| Situation | Behaviour |
|---|---|
| Both URLs succeed | Concatenated races, region-filtered, written to `paddypower.json` |
| One URL fails, other succeeds | stderr warning naming the failed URL; the successful URL's races are written |
| Both URLs fail | `PaddyClient` throws `IllegalStateException`; `Main.kt`'s existing catch prints `"Error fetching PaddyPower: …"` and exits 1. `betfair.json` (written earlier) is preserved. |
| Per-race parse error within either response | Race is dropped silently (existing parser behaviour) |
| One response is malformed JSON | The parse throws inside `PaddyResponses`; that one response yields no races; the other response (if it succeeded) still contributes its races. The fetcher does not exit. |

The "one URL fails, other succeeds" path is the new operational mode
introduced by this spec. The existing pipeline only had one URL, so
"partial success" wasn't possible.

## Tests

All tests pure; no live HTTP.

- **`PaddyNextRacesFetcherTest`** gains two new tests:
  - **"fetcher concatenates races from multiple client responses"** —
    constructs a fake `PaddyClient` (or extracts the parser
    invocation, depending on what's easiest given the existing
    structure) returning two synthetic JSON snippets: one with one GB
    race, one with one US race. Verifies the output `PaddyOutput`
    contains both races (count = 2) before any region filtering.
  - **"region filter selects only the requested region's races from
    the merged list"** — same two-snippet setup. With
    `regions = setOf("us")`, the output contains only the US race.
    With `regions = setOf("gb-ie")`, the output contains only the GB
    race. With `regions = setOf("gb-ie", "us")`, both are present.

- **`PaddyResponsesTest`** — unchanged. The single-response parser's
  behaviour is unaffected.

- **`PaddySchemaValidatorTest`** — unchanged. JSON schema is identical.

- **No `PaddyClient` per-URL try/catch tests.** Consistent with the
  existing decision: the live HTTP transport (Playwright) isn't
  unit-tested.

- **End-to-end smoke** (in the plan's final-validation task): run
  `./run.sh gb-ie,us`, confirm `paddypower.json` contains races from
  both regions, run `PaddyValidateMainKt` against it, run the arb
  finder, run `ArbValidateMainKt` against `arbs.json`.

## Acceptance

A run completes and produces a `paddypower.json` such that:

- A `./run.sh gb-ie,us` invocation contains races where
  `country == "US"` AND races where `country` is one of `"GB"`/`"IE"`.
- A `./run.sh` (default `gb-ie`) invocation contains only GB/IE races,
  same as before this spec — even though both URLs were fetched under
  the hood.
- A `./run.sh us` invocation contains only US races.
- `PaddySchemaValidator` reports zero errors in every case.
- `arbs.json` contains positive-margin opportunities joining Betfair US
  runners (already supported since the original Betfair design) to
  PaddyPower US runners when prices skew.
- If one of the two PaddyPower URLs returns an error or empty response,
  `paddypower.json` is still written with the other URL's races, and
  the user sees the per-URL warning on stderr.

## Migration

No schema migration. `paddypower.json` retains its exact shape; only
new races appear in the `races[]` array with `country: "US"`.
Existing consumers (arb finder, `PaddySchemaValidator`,
`PaddyValidateMain`) need no code changes.

## Open implementation questions

- **Exact US URL.** Discovered during Task 0 of the plan via DevTools
  capture on the PaddyPower US-racing page. We don't know in advance
  whether it's the same `apisms.paddypower.com` endpoint with a
  different `cardsToFetch=…` value, or a completely different URL —
  either case fits this spec because `PaddyClient` just stores the
  string verbatim.
- **Card stability across days.** Whether the US card id is stable
  across days (same concern as the existing GB/IE card). If it
  rotates, both URLs need re-capture. To be confirmed during the
  Task 9 smoke run on a different day.
- **JSON shape sanity.** The spec assumes the US response has the same
  shape as GB/IE. To be confirmed when the fixture is captured. If the
  shape differs, this spec is invalid and we'd revisit before
  proceeding.
