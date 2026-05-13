---
status: draft
date: 2026-05-14
topic: Each-way arbitrage calculator (Betfair lay vs PaddyPower back)
---

# Each-way arbitrage calculator

## Goal

Compute each-way arbitrage opportunities between PaddyPower's back-side
each-way prices and the Betfair Exchange's lay-side WIN + TOP_N markets,
producing a structured `arbs.json` ranked by margin. The output is the
data backbone for a future static site that displays the opportunities.

## Non-goals

- No pure win-only back/lay arbs. UK racing markets are too efficient
  for those to be a real opportunity. Each-way arbs are where the value
  lives, given PaddyPower's generous 1/5-odds-4-places terms.
- No automatic stake suggestion in the output. The calculator reports
  the per-£1 margin; the static site (or a human) computes stakes from
  the prices.
- No commission accounting. Margin is the raw mathematical surplus.
  The static site can subtract Betfair's 5% if it wants.
- No live scraping inside the calculator. It consumes existing
  `betfair.json` + `paddypower.json` snapshots.
- No scheduling, no continuous monitoring, no notifications.

## Prerequisites

- Existing `betfair.json` produced by the Betfair Exchange API scraper.
- Existing `paddypower.json` produced by the PaddyPower scraper.
- A small additive change to the Betfair output: `selectionId: Long?`
  on each runner. PaddyPower already exposes selection ids on its side;
  joining by id (rather than horse name) eliminates a fuzzy-matching
  failure mode.

## Approach

**Standalone Kotlin entry-point** in a new `com.horsey.scraper.arb`
sub-package. Reads the two JSON files, runs pure math, writes
`arbs.json`. `run.sh` chains `Main` (scrapers) → `ArbMain` so a single
invocation produces all three files. The arb logic is independently
runnable against archived snapshots, supporting the static-site
development loop.

## Module layout

### New sub-package: `src/main/kotlin/com/horsey/scraper/arb/`

- **`ArbModels.kt`** — domain types:

  ```kotlin
  data class PaddyPriceLeg(
      val winPrice: Double,
      val winPriceRaw: String,
      val eachWayTerms: EachWayTerms,
  )

  data class BetfairLayLeg(
      val winLay: Double,
      val topNLay: Double,
      val topNType: MarketType,  // TOP_2 | TOP_3 | TOP_4 | TOP_5
  )

  data class ArbRunner(
      val name: String,
      val selectionId: Long,
  )

  data class Arb(
      val venue: String,
      val country: String,
      val offTime: String,
      val marketName: String,
      val betfairWinMarketId: String,
      val runner: ArbRunner,
      val paddypower: PaddyPriceLeg,
      val betfair: BetfairLayLeg,
      val margin: Double,
  )

  data class ArbOutput(
      val computedAt: String,
      val betfairScrapedAt: String,
      val paddypowerScrapedAt: String,
      val arbCount: Int,
      val arbs: List<Arb>,
  )
  ```

- **`ArbCalculator.kt`** — pure compute:

  ```kotlin
  fun eachWayArbMargin(
      p: Double,    // PaddyPower win decimal odds
      f: Double,    // EW fraction in (0, 1]
      bw: Double,   // Betfair WIN lay decimal
      bp: Double,   // Betfair TOP_N lay decimal
  ): Double

  fun findArbs(
      betfair: ScrapeOutput,
      paddy: PaddyOutput,
  ): List<Arb>
  ```

  `eachWayArbMargin` is a pure function unit-tested standalone. `findArbs`
  is the orchestrator: joins races + runners, applies edge-case filters,
  computes margin per surviving (race, runner) tuple, returns the
  `margin > 0` results sorted by margin descending.

- **`ArbMain.kt`** — entry-point. Reads files, calls `findArbs`, writes
  `arbs.json` (Gson, pretty-printed, `serializeNulls()`). CLI:
  - 0 args: defaults — read `./betfair.json` and `./paddypower.json`,
    write `./arbs.json`.
  - 3 args: `<betfair-input> <paddypower-input> <output>` — all explicit.
  - Anything else (1, 2, 4+ args, `--help`, unknown flag): exit 1 with
    usage. Restricting to the two clear modes prevents the ambiguity of
    "is this one arg an input or an output?".

- **`ArbSchemaValidator.kt`** + **`ArbValidateMain.kt`** — mirrors the
  existing pattern for the other JSON outputs.

### Betfair-side prep (required for the join)

- **`Models.kt`**: `RunnerOdds` gains `selectionId: Long?`. Additive in
  the JSON output — `arbs.json` consumers can join by ID without
  horse-name normalisation.
- **`MarketScrape.runners`** changes from `List<Pair<String, Double?>>`
  to `List<RunnerEntry>` where:

  ```kotlin
  data class RunnerEntry(val selectionId: Long?, val name: String, val lay: Double?)
  ```

  Cleaner than threading a parallel id map through `assembleRaceOdds` /
  `pivotMarketScrapes`; one type carries everything about a
  runner-in-a-market.
- **`RaceOddsFetcher.kt`** `joinScrapes`: constructs `RunnerEntry` rather
  than `Pair`. The selection id flows from `winRunners` (already a list
  of `(Long, String)` pairs) into the `WIN` `MarketScrape` and the
  per-place `MarketScrape` rows.
- **`RunnerPivot.kt`**: uses the new `RunnerEntry` shape and propagates
  `selectionId` into each `RunnerOdds`. The phantom-horse warning logic
  is unchanged.
- **`SchemaValidator.kt`**: when present, `runners[].selectionId` must
  be a number (not a string, not a boolean). Optional, since older
  snapshots wouldn't have it.
- Tests for `RunnerPivotTest`, `RaceOddsAssemblyTest`, `ModelsJsonTest`,
  `SchemaValidatorTest`, `RaceOddsFetcherTest` update mechanically to
  carry/check the new field.

### `run.sh` chain

The existing `run.sh` invokes the scrapers via `./gradlew run … --args=…`.
Add a second invocation chained via `&&` that runs `ArbMainKt` with no
args (so it picks up the just-written files at default paths). A scrape
failure exits non-zero before the arb step is reached. End-to-end:
`./run.sh` → `betfair.json`, `paddypower.json`, `arbs.json`.

## Each-way arbitrage math

A PaddyPower each-way bet of stake **S** splits 50/50 between a Win leg
and a Place leg. Define:

| Symbol | Meaning |
|---|---|
| `p` | PaddyPower win decimal odds |
| `f` | EW fraction in `(0, 1]` (e.g. `0.2` for 1/5 odds) |
| `N` | EW number of paid places (must match a Betfair TOP_N market) |
| `bw` | Betfair WIN lay decimal |
| `bp` | Betfair TOP_N lay decimal (same N as PP's) |

Choose lay stakes `L_w` (on Betfair WIN) and `L_p` (on Betfair TOP_N).
Per **£1** of PaddyPower stake, the three outcome profits are:

- **Win:** `½(p + 1 + (p−1)·f) − 1 − L_w·(bw−1) − L_p·(bp−1)`
- **Place but not win:** `½(1 + (p−1)·f) − 1 + L_w − L_p·(bp−1)`
- **No place:** `−1 + L_w + L_p`

Setting all three equal yields a closed form:

```
L_w    = p / (2·bw)
L_p    = (1 + (p−1)·f) / (2·bp)
margin = L_w + L_p − 1
```

If `margin > 0`, it's an arb; the guaranteed profit per £1 PP stake is
exactly `margin`.

**Worked example.** PaddyPower offers 11.0 (10/1) on "Champ" with 1/5
odds, 4 places. Betfair lay-side offers WIN at 10.0 and TOP_4 at 2.5.

- `L_w = 11 / (2·10) = 0.55`
- `L_p = (1 + 10·0.2) / (2·2.5) = 0.60`
- `margin = 0.55 + 0.60 − 1 = 0.15`

A £100 PP stake (£50 win + £50 place) plus £55 lay at BF WIN and £60 lay
at BF TOP_4 produces +£15 profit in every outcome (Champ wins, Champ
places without winning, Champ doesn't place). Verified by per-outcome
cashflow expansion — see `EachWayArbMarginTest` for the test asserting
`0.15` to six decimal places.

**Equilibrium check.** When `bw == p` and `bp == 1 + (p−1)·f`,
`margin == 0` (the prices match the EW-implied levels exactly).
Anything tighter on the Betfair side → positive arb.

## Output schema (`arbs.json`)

```json
{
  "computedAt": "2026-05-13T22:35:00.123Z",
  "betfairScrapedAt": "2026-05-13T22:32:52.789Z",
  "paddypowerScrapedAt": "2026-05-13T22:32:54.042Z",
  "arbCount": 1,
  "arbs": [
    {
      "venue": "Clonmel",
      "country": "IE",
      "offTime": "2026-05-14T18:50:00+01:00",
      "marketName": "18:50 Clonmel - 2m1f Hcap Hrd",
      "betfairWinMarketId": "1.258114710",
      "runner": {
        "name": "Champ",
        "selectionId": 48920004
      },
      "paddypower": {
        "winPrice": 11.0,
        "winPriceRaw": "10/1",
        "eachWayTerms": { "fraction": 0.2, "places": 4 }
      },
      "betfair": {
        "winLay": 10.0,
        "topNLay": 2.5,
        "topNType": "TOP_4"
      },
      "margin": 0.15
    }
  ]
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `computedAt` | string, ISO-8601 UTC `Z` | `Instant.now()` at calculator run start |
| `betfairScrapedAt` | string, ISO-8601 UTC `Z` | copied from `betfair.json` top-level `scrapedAt` |
| `paddypowerScrapedAt` | string, ISO-8601 UTC `Z` | copied from `paddypower.json` top-level `scrapedAt` |
| `arbCount` | int | equals `arbs.length` |
| `arbs[].venue / country / offTime / marketName / betfairWinMarketId` | strings | as in source files; `country` is ISO 3166-1 alpha-2 |
| `arbs[].runner.name / selectionId` | string / number | identification |
| `arbs[].paddypower.winPrice` | number | decimal odds |
| `arbs[].paddypower.winPriceRaw` | string | original fractional |
| `arbs[].paddypower.eachWayTerms` | object `{ fraction: number ∈ (0,1], places: int 2..5 }` | structured |
| `arbs[].betfair.winLay` | number | decimal odds |
| `arbs[].betfair.topNLay` | number | decimal odds |
| `arbs[].betfair.topNType` | string ∈ `{TOP_2, TOP_3, TOP_4, TOP_5}` | matches `MarketType` enum |
| `arbs[].margin` | number, `> 0` | per-£1 PaddyPower-stake profit |

### Sort + filter rules

1. `arbs[]` is sorted by `margin` descending.
2. Only `margin > 0` entries are included.
3. No truncation. If 200 (race, runner) tuples have positive margins,
   all 200 are output.

### Edge-case rules

These are normative — they define what is and isn't a valid `arbs.json`.

1. A (race, runner) is considered iff the race appears in **both** input
   files (joined by `betfairWinMarketId`) AND the runner appears in both
   (joined by `selectionId`).
2. Skip races where PaddyPower's `eachWayTerms` is `null` (no EW on
   offer → no EW arb to compute).
3. Skip races where the Betfair `TOP_N` market matching
   `eachWayTerms.places` was not scraped successfully (key absent from
   that race's `marketScrapedAt`). No partial-arb reporting.
4. Skip runners where Betfair has no usable price on either side. Two
   distinct sub-cases, both treated identically:
   - The runner's `lay` map is missing the key entirely (the matching
     market wasn't scraped successfully — covered by rule 3 at the race
     level, but a single runner may also be missing from a market that
     was scraped).
   - The key is present but the value is `null` (scraped but no offer
     standing — Betfair edge-case rule 4).
5. Skip non-runners on the PaddyPower side (any of `winPrice`,
   `winPriceRaw` null).
6. `eachWayTerms.places` outside 2..5 → skip (we only scrape
   `TOP_2..TOP_5`).
7. Empty result is valid: `arbs.json` exists with `arbCount: 0`.

## Error policy

| Situation | Behaviour |
|---|---|
| Input file missing | exit 2, naming the path |
| Input file unparseable JSON | exit 2 with the parser message |
| Input file fails its own schema validator | exit 2 with the first error |
| No races in either input | exit 0, write `arbs.json` with `arbCount: 0` |
| Zero arbs computed (no positive margins) | exit 0, write `arbs.json` with `arbCount: 0` |
| Per-race calculation throws | log to stderr, skip that race, continue |

Exit-code distinction from the scrapers: scrapers use `1` for
fetch/login/network errors and `2` for credentials. The arb calculator
uses `2` for "input data problems" and `0` for "ran cleanly even if zero
arbs". No `1` case in v1; the calculator is deterministic file IO + math
and has no network or credentials surface.

## CLI

Two modes, no ambiguous middle ground:

```text
ArbMain                                                     # all defaults
ArbMain <betfair-in.json> <paddy-in.json> <arbs-out.json>   # all explicit
```

Anything else (1, 2, 4+ args, `--help`, unknown flag) → exit `1` with
usage. The spec deliberately avoids 1-arg and 2-arg forms because they
require a positional convention ("is this an input or an output?") that
adds error surface for no real workflow benefit.

## Testing

All tests pure, no live HTTP, no live file IO except temp-file reads.

- **`EachWayArbMarginTest`** — the headline math function:
  - Champ example (`p=11`, `f=0.2`, `bw=10`, `bp=2.5`) → `0.15` to 6dp.
  - Equilibrium (`bw == p`, `bp == 1 + (p−1)·f`) → `0.0` exactly.
  - Negative-margin case (BF prices wider than equilibrium) → returns
    a negative number.
  - Boundary: `bp = 1.0` produces a finite (huge) result, not NaN.
  - Boundary: `f = 0.0` rejected at the calculator orchestrator; the
    pure function itself returns the formula's value (which collapses
    to a degenerate case).

- **`FindArbsTest`** — orchestration over canned `ScrapeOutput` +
  `PaddyOutput` instances:
  - One race, one runner, prices skewed → returns one `Arb`.
  - One race, one runner, prices at equilibrium → returns empty.
  - Race in PP only → skipped silently.
  - Race in BF only → skipped silently.
  - Runner in PP race but not BF race (selectionId mismatch) → skipped.
  - PP race with `eachWayTerms == null` → all its runners skipped.
  - PP race wants `places=4` but BF race scraped only `WIN + TOP_2` →
    all runners skipped.
  - Output sorted by margin descending.
  - Multiple races, multiple runners → ordering and count correct.

- **`ArbSchemaValidatorTest`** — happy path + each rule that can be
  violated (missing required field, non-ISO timestamp, `margin <= 0`,
  unknown `topNType`, EW out of range, `arbCount` mismatch).

- **`PriceLegConstructionTest`** — small test that `arbs[].paddypower`
  and `arbs[].betfair` faithfully copy the source values used in the
  margin calc (no rounding loss; types intact through Gson roundtrip).

- **No live e2e tests.** Verification path: `./run.sh` end-to-end
  followed by `./gradlew run -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=arbs.json`.

### Betfair-side prep tests

These ride along with the implementation plan, not new arb tests:

- `RunnerPivotTest` extended to cover `selectionId` propagation through
  the new `RunnerEntry` type into `RunnerOdds`.
- `SchemaValidatorTest` extended with a runner that has and doesn't
  have `selectionId` (validator must accept both).
- `RaceOddsFetcherTest` updated for the `RunnerEntry` shape change in
  `MarketScrape.runners`.
- `RaceOddsAssemblyTest` and `ModelsJsonTest` updated mechanically.

## Acceptance

A run with valid input snapshots completes within seconds and produces
an `arbs.json` such that:

- Top-level shape matches the schema.
- `ArbSchemaValidator` reports zero errors.
- For each entry, the closed-form `margin` value matches the value
  recomputed from the inline price legs to within 1e-9 (no transcription
  errors between the calculator and the JSON).
- A `./run.sh` end-to-end produces all three of `betfair.json`,
  `paddypower.json`, `arbs.json`.
- A consumer reading just `arbs.json` has everything needed to render a
  static page (race metadata, runner metadata, both-side prices,
  margin) without referring back to the source files.

## Migration

No schema breakage to existing files: `betfair.json` gains a new
optional `selectionId` field on each runner (additive — older snapshots
without the field continue to validate). `paddypower.json` is unchanged.
`arbs.json` is new and has no existing consumers.

## Out of scope (future)

- Continuous monitoring / re-running on price ticks.
- Bankroll-scaled stake outputs.
- Commission accounting (5% Betfair default).
- Liquidity-aware arbs (factoring `availableToLay[0].size`).
- Historical arb archive / time-series.
- More bookmakers on the back side; multi-way arbs.
- The static site itself (separate project).
