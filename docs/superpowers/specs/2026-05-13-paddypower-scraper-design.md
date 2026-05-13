---
status: draft
date: 2026-05-13
topic: PaddyPower bookmaker scraper (first of N bookmaker sources)
---

# PaddyPower bookmaker scraper

## Goal

Add the first bookmaker-side data source to the repo: a one-shot scraper
that reads PaddyPower's "next races" view and writes
`paddypower.json` — a self-contained snapshot of horse names, win
prices, and each-way terms, suitable for arb-comparison against the
Betfair lay-side `data.json` already produced by this repo.

This is the first of N bookmaker scrapers (Bet365, William Hill, etc.
to come). The design treats PaddyPower as one concrete instance of a
pattern, and the output file is per-bookmaker so additional ones slot
in without disturbing each other.

## Non-goals

- No automated arb-comparison. Producing the bookmaker snapshot is the
  scope; joining it against `data.json` is a future tool.
- No full-day scrape. v1 captures only what PaddyPower shows on the
  next-races landing page (typically 5–10 upcoming races globally,
  filtered to GB+IE by default).
- No back-side ladder, no stake sizing, no historical capture. Single
  best-back price per runner, one snapshot per run, overwriting
  `paddypower.json`.
- No retries, no rate-limit handling. One HTTP call per run.

## Prerequisites

- None new. Existing JDK 17 + Gradle stack is sufficient.
- PaddyPower's next-races view is public (no auth, no account).
- We assume the page is JS-rendered and backed by an internal JSON
  endpoint that the design will discover at implementation time. If
  that assumption fails, the documented fallback is Playwright
  (`com.microsoft.playwright:playwright`) — added as a Gradle dep at
  that point.

## Approach

**Hand-rolled HTTP**, mirroring the Betfair API client we built in the
previous migration. A small `PaddyClient` wraps `java.net.http.HttpClient`
with a realistic Chrome `User-Agent` and a single method,
`getNextRaces()`, that hits the discovered endpoint. Pure parsers turn
the JSON into domain types. The PaddyPower scrape runs from `Main.kt`
*after* the Betfair pipeline so a PP failure cannot lose Betfair output.

## Module layout

### New sub-package: `src/main/kotlin/com/horsey/scraper/paddypower/`

- **`PaddyClient.kt`** — HTTP transport. Constructor takes no args.
  Holds a `HttpClient`. Sets `User-Agent` to a realistic Chrome UA and
  `Accept: application/json`. One method: `fun getNextRaces(): String`.
  Non-2xx → `IllegalStateException` with status code + first 500 chars
  of body, same shape as `BetfairClient.sendForBody`.

- **`PaddyModels.kt`** — domain types:

  ```kotlin
  data class EachWayTerms(val fraction: Double, val places: Int)

  data class PaddyRunner(
      val name: String,
      val winPrice: Double?,     // decimal odds; null for non-runners
      val winPriceRaw: String?,  // original fractional; null for non-runners
  )

  data class PaddyRace(
      val venue: String,
      val country: String,       // "GB" | "IE" | "US" | ...
      val offTime: String,       // ISO-8601 with Europe/London offset
      val marketName: String,    // "HH:mm Venue"
      val raceUrl: String,
      val scrapedAt: String,     // ISO-8601 UTC `Z`
      val eachWayTerms: EachWayTerms?,
      val runners: List<PaddyRunner>,
  )

  data class PaddyOutput(
      val scrapedAt: String,     // run start, ISO-8601 UTC `Z`
      val raceCount: Int,
      val races: List<PaddyRace>,
  )
  ```

- **`PaddyResponses.kt`** — pure parsers:
  - `fun fractionalToDecimal(raw: String): Double?` —
    `"9/2"`→`5.5`, `"evens"`/`"EVS"`/`"1/1"`→`2.0`, `"SP"`/malformed→`null`.
  - `fun parseEachWayTerms(raw: String): EachWayTerms?` — accepts
    common PP formats; returns `null` on missing or unrecognised input.
  - `fun parsePaddyNextRaces(json: String, nowProvider: () -> Instant = { Instant.now() }): List<PaddyRace>` —
    shreds the response into `PaddyRace` objects. Per-race `scrapedAt`
    timestamps come from the injected `nowProvider`. Races without a
    country, with no parseable runners, or with otherwise broken
    fixtures are dropped with a stderr warning.

- **`PaddyNextRacesFetcher.kt`** — orchestration. Constructor takes
  `PaddyClient`. One method:
  `fun fetch(regions: Set<String>): PaddyOutput`. Calls the client,
  invokes the parser, filters races by `Regions.countriesForAll(regions)`,
  packages the result with the run-start timestamp.

- **`PaddySchemaValidator.kt`** + **`PaddyValidateMain.kt`** — mirror
  the existing `SchemaValidator` / `ValidateMain` pattern. Run via
  `./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json`.

### Files modified outside the sub-package

- **`Main.kt`** — appends a second pipeline after the Betfair scrape:

  ```text
  (existing Betfair pipeline, unchanged)
    → write data.json
  PaddyPower pipeline (only if Betfair phase exited cleanly):
    val ppFetcher = PaddyNextRacesFetcher(PaddyClient())
    val ppOutput = try {
        ppFetcher.fetch(regions)
    } catch (e: Exception) {
        System.err.println("Error fetching PaddyPower: ${e.message}")
        kotlin.system.exitProcess(1)
    }
    File("paddypower.json").writeText(gson.toJson(ppOutput))
  ```

  Same `regions` arg controls both scrapes. Default `gb-ie` (existing).

Nothing else changes: `Regions`, `Credentials`, `BetfairClient`,
`RaceListFetcher`, `RaceOddsFetcher`, `RunnerPivot`, the Betfair
`SchemaValidator` — all untouched.

## Output schema (`paddypower.json`)

```json
{
  "scrapedAt": "2026-05-13T20:30:00.123Z",
  "raceCount": 7,
  "races": [
    {
      "venue": "Punchestown",
      "country": "IE",
      "offTime": "2026-05-13T20:20:00+01:00",
      "marketName": "20:20 Punchestown",
      "raceUrl": "https://www.paddypower.com/horse-racing/race/...",
      "scrapedAt": "2026-05-13T20:30:00.456Z",
      "eachWayTerms": { "fraction": 0.2, "places": 3 },
      "runners": [
        {
          "name": "Working Class Hero",
          "winPrice": 5.5,
          "winPriceRaw": "9/2"
        },
        {
          "name": "Mister Killeens",
          "winPrice": null,
          "winPriceRaw": null
        }
      ]
    }
  ]
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `scrapedAt` (top) | string, ISO-8601 UTC `Z` | `Instant.now()` at PP run start |
| `raceCount` | int | equals `races.length` |
| `races[].venue` | string | as shown on PaddyPower |
| `races[].country` | string | ISO 3166-1 alpha-2 (`GB`, `IE`, `US`, …) |
| `races[].offTime` | string, ISO-8601 with offset | Europe/London offset; matches Betfair format exactly |
| `races[].marketName` | string | `"HH:mm Venue"` (race-type suffix only if PP exposes it cleanly; see Open Questions) |
| `races[].raceUrl` | string | PaddyPower deep link, useful for debugging |
| `races[].scrapedAt` | string, ISO-8601 UTC | per-race observation time |
| `races[].eachWayTerms` | object or `null` | `{ fraction: Double in (0,1], places: Int 1..6 }`; `null` when PP doesn't offer EW |
| `races[].runners[].name` | string | as shown on PaddyPower |
| `races[].runners[].winPrice` | number or `null` | decimal odds; `null` for non-runners or unparseable prices |
| `races[].runners[].winPriceRaw` | string or `null` | original fractional; `null` for non-runners or unparseable prices |

### Edge-case rules

These are normative — they define what is and isn't a valid `paddypower.json`.

1. A race is in the output iff it appears on the next-races view AND
   passes the region filter.
2. Non-runners (or runners with unparseable prices) remain in
   `runners[]` with `winPrice: null` and `winPriceRaw: null`. Matching
   names against the Betfair runner list is useful even when prices
   are unavailable.
3. A race with zero parseable runners is dropped with a stderr warning.
4. A race without a country code is dropped (the region filter would
   be unsafe otherwise) with a stderr warning.
5. `eachWayTerms` is `null` when PP doesn't display them. We don't
   fabricate values.
6. The join key against Betfair's `data.json` is the tuple
   `(country, venue, offTime)`. Both sides format `offTime` identically
   (Europe/London offset, no sub-second precision) so a string compare
   suffices. Venue-name normalisation (e.g. PP "Lingfield Park" vs
   Betfair "Lingfield") is a known mismatch surface and will be
   handled by the future arb-finder; this spec does not normalise on
   the scrape side.
7. `winPrice` and `winPriceRaw` are both null or both populated — the
   validator enforces parity.

## Error policy

| Situation | Behaviour |
|---|---|
| HTTP error fetching next-races | exit 1, no `paddypower.json` written |
| Single race with unparseable JSON entry | log warning, skip that race, keep the rest |
| Race with zero parseable runners | log warning, drop |
| Race with no country info | log warning, drop |
| Empty result after region filter | write valid `paddypower.json` with `raceCount: 0` |
| Single runner with unparseable price | runner kept, both price fields null |

The PaddyPower phase runs *after* the Betfair phase completes
successfully. If PP fails, `data.json` is already on disk so the
Betfair scrape is preserved; the process exits 1 to signal the
incomplete run.

## CLI

No CLI change. The existing single positional `regions` arg
(`./run.sh`, `./run.sh us`, `./run.sh gb-ie,us`) controls both scrapes.
Default `gb-ie`.

## Testing

All tests pure, no live HTTP. New unit tests:

- **`FractionToDecimalTest`** — happy paths (`"9/2"`→`5.5`,
  `"5/2"`→`3.5`, `"1/1"`→`2.0`), word forms (`"evens"`/`"EVS"`→`2.0`),
  unparseable (`"SP"`, `""`, `null`-ish, garbage) → `null`.
- **`EachWayTermsParserTest`** — common PP formats
  (`"1/5 Odds, 3 Places"`, `"1/4 odds 1,2,3,4"`), missing input,
  unrecognised formats.
- **`PaddyResponsesTest`** — `parsePaddyNextRaces` over a canned JSON
  fixture: race + runner shredding, non-runner handling, races
  without country dropped, races without runners dropped, EW present
  vs null.
- **`PaddyNextRacesFetcherTest`** — region filter applied correctly to
  a fixed race list (no live HTTP; uses a fake client or pure
  function decomposition).
- **`PaddySchemaValidatorTest`** — happy path, missing top-level
  fields, EW out of range, decimal/raw parity violation,
  `raceCount` mismatch, `winPrice` value type errors.

No live API tests. End-to-end verification is a manual smoke run +
`PaddyValidateMain`.

## Acceptance

A run with the existing Betfair credentials configured completes,
produces both `data.json` and a `paddypower.json` such that:

- Top-level shape matches the schema above.
- `PaddySchemaValidator` reports zero errors.
- For at least one race, the runner list non-trivially overlaps with
  the corresponding Betfair race's runners by name (manual eyeball
  check — programmatic matching is the arb-finder's job).
- `eachWayTerms` is non-null and structurally valid for at least one
  race that PP offers EW on.
- A non-runner (if present on the day) appears in the runner list
  with both price fields null.

For a day when the next-races view contains no GB/IE races: the file
exists with `raceCount: 0` and the run exits 0 (after the Betfair
phase succeeded).

## Migration

No schema breakage. `data.json` is unchanged; `paddypower.json` is new
and has no existing consumers.

## Open implementation questions

These will be resolved during implementation, not blocking on design:

- **Exact next-races endpoint URL.** Discovered via Chrome DevTools →
  Network tab during implementation. If discoverable: hand-rolled
  HTTP as designed. If only delivered via WebSocket / heavy JS hydration:
  switch to Playwright (`com.microsoft.playwright:playwright`) — adds
  a Gradle dep but keeps the rest of the design intact.
- **Word-form prices.** Whether "evens" / "EVS" appear in the API
  payload or only `1/1`. Parser handles both; tests cover both.
- **Race-type snippet.** Whether PP exposes a clean
  `5f Hcap`-style descriptor; if yes, the `marketName` becomes
  `"HH:mm Venue - <type>"` to match the Betfair format; if not,
  it stays as `"HH:mm Venue"`.
- **Non-runner marking.** Whether PP flags non-runners with an
  explicit field (`status: "NON_RUNNER"`) or by an absent price;
  parser handles both via the "both fields null" rule.
- **Venue-name normalisation.** PP may show venues as "Lingfield Park"
  where Betfair shows "Lingfield". Out of scope; flagged for the
  future arb-finder.
- **Country source.** If the API payload does not include a country code
  per race, edge-case rule 4 would silently drop every race. In that
  case we re-introduce a venue → country lookup table (analogous to the
  deleted `Venues.kt`, scoped to GB+IE venues PP actually shows on
  next-races) at implementation time and resolve country via lookup
  before applying the region filter.
