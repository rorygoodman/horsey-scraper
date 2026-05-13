# Each-Way Arbitrage Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone CLI that consumes `betfair.json` + `paddypower.json` and writes `arbs.json` — a ranked list of each-way arbitrage opportunities (back EW at PaddyPower, lay WIN + matching TOP_N at Betfair).

**Architecture:** New sub-package `com.horsey.scraper.arb` containing pure-math (`eachWayArbMargin`), an orchestrator (`findArbs`), models, and an entry point (`ArbMain`) that round-trips JSON through Gson against the existing `ScrapeOutput` / `PaddyOutput` models. Two prep tasks on the Betfair side first: add `selectionId` to runners so the join is by ID rather than horse name. `run.sh` chains scrapers → arb finder.

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`, Gson. No new Maven dependencies.

**Spec:** `docs/superpowers/specs/2026-05-14-arb-finder-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- This is a Kotlin/JVM repo with three existing pieces: a Betfair Exchange API scraper writing `betfair.json`, a PaddyPower scraper writing `paddypower.json`, and a `Main.kt` that orchestrates both. You're adding a third stage that reads those two files and writes `arbs.json`.
- Output schemas of the two input files: see `docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md` (Betfair) and `docs/superpowers/specs/2026-05-13-paddypower-scraper-design.md` (PaddyPower).
- The existing pattern: per-feature sub-package, pure data parsers, a thin Main, a separate validator + ValidateMain entry-point. Follow it.
- TDD throughout. Tests live under `src/test/kotlin/com/horsey/scraper/arb/` (and the existing test packages for the Betfair-side prep work).
- Test baseline at the start of Task 1: 143 tests (verify with `./gradlew test`). Each task adds tests; the plan states the expected new count after each.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

### About the `MarketScrape.runners` change in Task 2

This is the most invasive bit of the plan. `MarketScrape.runners: List<Pair<String, Double?>>` becomes `List<RunnerEntry>` where `RunnerEntry` is a tiny data class carrying `(selectionId, name, lay)`. Every test that currently writes `listOf("X" to 3.0)` will need to become `listOf(RunnerEntry(null, "X", 3.0))` (or with a real selection id). The change is mechanical — sed-style — but it touches several files. The reward is that the runner-level join in `findArbs` can be by selection id, eliminating horse-name normalisation as a failure mode.

---

## Task 1: Add `selectionId: Long?` to `RunnerOdds`

Tiny additive change. `selectionId` defaults to `null` so existing constructors keep working. The schema validator gains one rule for the new field. No behavioural change yet — Task 2 is what populates the field with real values from the API.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Models.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/SchemaValidator.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt`

- [ ] **Step 1: Write the failing test (validator accepts the new field)**

Open `src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt`. Find the existing class body. Add three new tests just before the closing `}`:

```kotlin
    @Test
    fun `selectionId field on a runner is accepted when present and numeric`() {
        // Take the existing happy-path JSON and inject a selectionId on the runner.
        val withSelectionId = HAPPY_PATH_JSON.replace(
            "\"name\": \"Some Horse\",",
            "\"name\": \"Some Horse\", \"selectionId\": 12345,"
        )
        assertEquals(emptyList(), validateScrapeOutput(withSelectionId))
    }

    @Test
    fun `selectionId field absent is also accepted (backward compatibility)`() {
        // The existing happy path has no selectionId field — still valid.
        assertEquals(emptyList(), validateScrapeOutput(HAPPY_PATH_JSON))
    }

    @Test
    fun `selectionId of wrong type is flagged`() {
        val bad = HAPPY_PATH_JSON.replace(
            "\"name\": \"Some Horse\",",
            "\"name\": \"Some Horse\", \"selectionId\": \"not a number\","
        )
        val errs = validateScrapeOutput(bad)
        assertTrue(errs.any { "selectionId" in it }, errs.toString())
    }
```

`HAPPY_PATH_JSON` is whatever the existing happy-path constant is in this file (find it near the top of the class — it's the string used by the first test). If the existing file uses a different inline-fixture pattern, follow that pattern instead and inject `"selectionId": 12345,` after `"name": "..."` on a runner of your choice. The point is to exercise the validator's new rule.

- [ ] **Step 2: Write the failing test (Models JSON serialises selectionId)**

Open `src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt`. Find the existing test that serialises a `RunnerOdds`. Add one new test just before the closing `}`:

```kotlin
    @Test
    fun `RunnerOdds serialises selectionId when set`() {
        val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()
        val runner = RunnerOdds(
            name = "X",
            lay = linkedMapOf(MarketType.WIN to 4.5),
            selectionId = 987654321L,
        )
        val json = gson.toJson(runner)
        assertTrue(json.contains("\"selectionId\": 987654321"), json)
    }

    @Test
    fun `RunnerOdds serialises selectionId as null when unset`() {
        val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()
        val runner = RunnerOdds(name = "X", lay = linkedMapOf(MarketType.WIN to 4.5))
        val json = gson.toJson(runner)
        assertTrue(json.contains("\"selectionId\": null"), json)
    }
```

If `GsonBuilder` isn't imported at the top of the file, add it: `import com.google.gson.GsonBuilder`.

- [ ] **Step 3: Run new tests, verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.ModelsJsonTest' --tests 'com.horsey.scraper.SchemaValidatorTest'`

Expected: compilation failures referencing `selectionId` (because the field doesn't exist on `RunnerOdds` yet) and validator rule failure.

- [ ] **Step 4: Add `selectionId` to `RunnerOdds`**

Open `src/main/kotlin/com/horsey/scraper/Models.kt`. Find the existing `RunnerOdds` declaration:

```kotlin
data class RunnerOdds(
    val name: String,
    val lay: Map<MarketType, Double?>
)
```

Replace with (note the field added at the END with default `null` for backward compatibility with existing positional and named constructors):

```kotlin
/**
 * One runner's lay prices pivoted across markets. Key presence in `lay`
 * mirrors key presence in [RaceOdds.marketScrapedAt]: present iff the
 * market was scraped successfully.
 *
 * `selectionId` is the Betfair Exchange selection id for this runner.
 * It exists primarily so a downstream arbitrage tool can join Betfair
 * runners to PaddyPower runners (which expose the same id) without
 * horse-name normalisation. Nullable for backward compatibility with
 * older snapshots and tests that don't care about the id.
 */
data class RunnerOdds(
    val name: String,
    val lay: Map<MarketType, Double?>,
    val selectionId: Long? = null,
)
```

- [ ] **Step 5: Add the validator rule for `selectionId`**

Open `src/main/kotlin/com/horsey/scraper/SchemaValidator.kt`. Find the runner-level loop (the block that calls `requireString(r, "name", errors)`). Just after that line, add:

```kotlin
            // selectionId is optional; when present it must be a JSON number.
            val selEl = r.get("selectionId")
            if (selEl != null && !selEl.isJsonNull) {
                if (!selEl.isJsonPrimitive || !selEl.asJsonPrimitive.isNumber) {
                    errors += "$rctx.selectionId: not a number (got $selEl)"
                }
            }
```

`$rctx` is the existing per-runner context string (the validator already constructs it for the `name`/`lay` checks).

- [ ] **Step 6: Run new tests, verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.ModelsJsonTest' --tests 'com.horsey.scraper.SchemaValidatorTest'`

Expected: all tests in those two files pass, including the three new validator tests and two new Models tests.

- [ ] **Step 7: Run the full suite**

Run: `./gradlew test`

Expected: 148 tests pass (143 baseline + 5 new in this task).

- [ ] **Step 8: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Models.kt \
        src/main/kotlin/com/horsey/scraper/SchemaValidator.kt \
        src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt \
        src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt
git commit -m "Add RunnerOdds.selectionId (additive, default null)"
```

---

## Task 2: Replace `MarketScrape.runners` with `RunnerEntry`; populate `selectionId` from the API

The model carrier of "what we know about a runner in a market" is currently a `Pair<String, Double?>`. Replace with a small data class `RunnerEntry(selectionId, name, lay)` so the selection id can travel from the API response (which already has it) all the way into `RunnerOdds`.

This task has substantial test churn — every existing test that constructs a `MarketScrape` with `listOf("X" to 3.0)`-style pairs needs to be rewritten as `listOf(RunnerEntry(null, "X", 3.0))`. The change is mechanical.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Models.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/RunnerPivot.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/RaceOddsAssemblyTest.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt`

- [ ] **Step 1: Write the failing test (selectionId propagates through the pivot)**

Open `src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt`. Add a new test just before the closing `}` of the existing test class:

```kotlin
    @Test
    fun `selectionId from the WIN scrape propagates into RunnerOdds`() {
        val win = MarketScrape(
            MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf(RunnerEntry(selectionId = 111L, name = "X", lay = 3.0)),
        )
        val top3 = MarketScrape(
            MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf(RunnerEntry(selectionId = 111L, name = "X", lay = 1.5)),
        )
        val pivoted = pivotMarketScrapes(
            scrapes = linkedMapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.999",
        )
        assertEquals(1, pivoted.size)
        assertEquals(111L, pivoted[0].selectionId)
        assertEquals("X", pivoted[0].name)
    }

    @Test
    fun `selectionId is null on RunnerOdds when WIN scrape carries a null id`() {
        val win = MarketScrape(
            MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf(RunnerEntry(selectionId = null, name = "Y", lay = 5.0)),
        )
        val pivoted = pivotMarketScrapes(
            scrapes = linkedMapOf(MarketType.WIN to win),
            raceIdForWarnings = "1.999",
        )
        assertEquals(1, pivoted.size)
        assertEquals(null, pivoted[0].selectionId)
    }
```

- [ ] **Step 2: Run new test, verify it fails to compile**

Run: `./gradlew test --tests 'com.horsey.scraper.RunnerPivotTest'`

Expected: compilation failure on `RunnerEntry` (doesn't exist yet).

- [ ] **Step 3: Add `RunnerEntry` to `Models.kt` and change `MarketScrape.runners` type**

Open `src/main/kotlin/com/horsey/scraper/Models.kt`. Find the `MarketScrape` declaration:

```kotlin
data class MarketScrape(
    val type: MarketType,
    val scrapedAt: String,
    val runners: List<Pair<String, Double?>>
)
```

Replace with:

```kotlin
/**
 * One runner observed in one market scrape. `selectionId` is the
 * Betfair selection id (when known); `name` is the horse name as
 * shown on the market page; `lay` is the best lay price observed
 * (or null if no lay was on offer).
 */
data class RunnerEntry(
    val selectionId: Long?,
    val name: String,
    val lay: Double?,
)

/**
 * Result of scraping a single market within a race. Intermediate type
 * passed from per-market scrape into the pivot. Not serialised.
 *
 * `scrapedAt` is an ISO-8601 UTC instant (e.g. "2026-05-09T12:00:04Z").
 * `runners` preserves market-page order; the lay value is null if no
 * lay is on offer for that runner.
 */
data class MarketScrape(
    val type: MarketType,
    val scrapedAt: String,
    val runners: List<RunnerEntry>
)
```

- [ ] **Step 4: Update `RaceOddsFetcher.joinScrapes` to construct `RunnerEntry`**

Open `src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt`. Find this block inside `joinScrapes`:

```kotlin
        val scrapes = linkedMapOf<MarketType, MarketScrape>(
            MarketType.WIN to MarketScrape(
                type = MarketType.WIN,
                scrapedAt = scrapedAt,
                runners = nameOrder.map { (sel, name) -> name to winSnap.layBySelectionId[sel] },
            )
        )
```

Replace the inner `runners = ...` line with:

```kotlin
                runners = nameOrder.map { (sel, name) ->
                    RunnerEntry(selectionId = sel, name = name, lay = winSnap.layBySelectionId[sel])
                },
```

Then find the per-place scrape construction further down:

```kotlin
            val rows = place.runners.entries.map { (sel, name) ->
                name to snap.layBySelectionId[sel]
            }
            scrapes[place.type] = MarketScrape(
                type = place.type,
                scrapedAt = scrapedAt,
                runners = rows,
            )
```

Replace with:

```kotlin
            val rows = place.runners.entries.map { (sel, name) ->
                RunnerEntry(selectionId = sel, name = name, lay = snap.layBySelectionId[sel])
            }
            scrapes[place.type] = MarketScrape(
                type = place.type,
                scrapedAt = scrapedAt,
                runners = rows,
            )
```

- [ ] **Step 5: Update `RunnerPivot.pivotMarketScrapes` to use `RunnerEntry`**

Open `src/main/kotlin/com/horsey/scraper/RunnerPivot.kt`. Find the existing function body:

```kotlin
    val winNames: Set<String> = win.runners.map { it.first }.toSet()
    val orderedTypes = MarketType.values().filter { it in scrapes }

    // Phantom-horse warnings: anyone in a scraped Top-N market but not in WIN.
    for (type in orderedTypes) {
        if (type == MarketType.WIN) continue
        for ((name, _) in scrapes.getValue(type).runners) {
            if (name !in winNames) {
                System.err.println("Phantom horse '$name' in $type for race $raceIdForWarnings — dropping")
            }
        }
    }

    return win.runners.map { (name, _) ->
        val lay = linkedMapOf<MarketType, Double?>()
        for (type in orderedTypes) {
            val market = scrapes.getValue(type)
            // Find this horse's entry in this market (null if absent or no offer).
            val entry = market.runners.firstOrNull { it.first == name }
            lay[type] = entry?.second
        }
        RunnerOdds(name = name, lay = lay)
    }
```

Replace with:

```kotlin
    val winNames: Set<String> = win.runners.map { it.name }.toSet()
    val orderedTypes = MarketType.values().filter { it in scrapes }

    // Phantom-horse warnings: anyone in a scraped Top-N market but not in WIN.
    for (type in orderedTypes) {
        if (type == MarketType.WIN) continue
        for (entry in scrapes.getValue(type).runners) {
            if (entry.name !in winNames) {
                System.err.println("Phantom horse '${entry.name}' in $type for race $raceIdForWarnings — dropping")
            }
        }
    }

    return win.runners.map { winEntry ->
        val lay = linkedMapOf<MarketType, Double?>()
        for (type in orderedTypes) {
            val market = scrapes.getValue(type)
            // Find this horse's entry in this market (null if absent or no offer).
            val entry = market.runners.firstOrNull { it.name == winEntry.name }
            lay[type] = entry?.lay
        }
        RunnerOdds(name = winEntry.name, lay = lay, selectionId = winEntry.selectionId)
    }
```

- [ ] **Step 6: Update `RunnerPivotTest` existing fixtures (mechanical)**

Open `src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt`. Every existing `listOf("X" to 3.0)`, `listOf("X" to 1.5)`, `listOf("X" to null)`, etc. needs to become `listOf(RunnerEntry(null, "X", 3.0))` and so on. Multi-runner cases like `listOf("A" to 2.0, "B" to 5.0)` become `listOf(RunnerEntry(null, "A", 2.0), RunnerEntry(null, "B", 5.0))`.

The new tests added in Step 1 already use `RunnerEntry` directly — leave them.

If you want to use a sed-like replacement: every `"<name>" to <value>` inside a `listOf(...)` argument passed to `MarketScrape(...)` becomes `RunnerEntry(null, "<name>", <value>)`. Verify visually after the bulk change.

- [ ] **Step 7: Update `RaceOddsAssemblyTest` existing fixtures (mechanical)**

Open `src/test/kotlin/com/horsey/scraper/RaceOddsAssemblyTest.kt`. Same pattern as Step 6 — every `"X" to 3.0`-style pair inside a `MarketScrape(...)` constructor becomes `RunnerEntry(null, "X", 3.0)`.

- [ ] **Step 8: Update `RaceOddsFetcherTest` existing fixtures (mechanical)**

Open `src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt`. Look for any `MarketScrape(...)` constructors with pair-style runners and convert. (This file's tests are mostly about the JSON-parsing helpers and may not directly construct MarketScrape — only do the mechanical change where the compiler complains.)

- [ ] **Step 9: Compile everything**

Run: `./gradlew compileKotlin compileTestKotlin`

Expected: `BUILD SUCCESSFUL`. If you get unresolved-reference errors on `Pair`, `first`, `second`, you missed a spot in Steps 6–8.

- [ ] **Step 10: Run the new selectionId-propagation tests**

Run: `./gradlew test --tests 'com.horsey.scraper.RunnerPivotTest'`

Expected: all RunnerPivotTest tests pass, including the two new ones from Step 1.

- [ ] **Step 11: Run the full suite**

Run: `./gradlew test`

Expected: 150 tests pass (148 baseline from Task 1 + 2 new from this task). All 148 prior tests still green; the 2 new tests added in Step 1 now pass.

- [ ] **Step 12: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Models.kt \
        src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt \
        src/main/kotlin/com/horsey/scraper/RunnerPivot.kt \
        src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt \
        src/test/kotlin/com/horsey/scraper/RaceOddsAssemblyTest.kt \
        src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt
git commit -m "Replace MarketScrape.runners with RunnerEntry; propagate selectionId into RunnerOdds"
```

---

## Task 3: `ArbModels.kt` — domain types

Create the data classes for the new sub-package. No tests — Kotlin's `data class` machinery is compiler-generated.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/arb/ArbModels.kt`

- [ ] **Step 1: Create the file**

```kotlin
package com.horsey.scraper.arb

import com.horsey.scraper.MarketType
import com.horsey.scraper.paddypower.EachWayTerms

/**
 * The PaddyPower-side prices used when computing one arb. Captured into
 * the output so the static-site consumer can recompute lay stakes from
 * the same numbers the calculator used.
 */
data class PaddyPriceLeg(
    val winPrice: Double,
    val winPriceRaw: String,
    val eachWayTerms: EachWayTerms,
)

/**
 * The Betfair-side lay prices used when computing one arb. `topNType`
 * names the specific TOP_N market chosen (matches PaddyPower's
 * `eachWayTerms.places`).
 */
data class BetfairLayLeg(
    val winLay: Double,
    val topNLay: Double,
    val topNType: MarketType,
)

/** Identification for one runner in an arb result. */
data class ArbRunner(
    val name: String,
    val selectionId: Long,
)

/**
 * One each-way arbitrage opportunity. `margin` is the per-£1
 * PaddyPower-stake profit, > 0 by construction (negative-margin
 * results are filtered out before reaching `arbs[]`).
 */
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

/** Top-level wrapper for `arbs.json`. */
data class ArbOutput(
    val computedAt: String,
    val betfairScrapedAt: String,
    val paddypowerScrapedAt: String,
    val arbCount: Int,
    val arbs: List<Arb>,
)
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Run the full suite**

Run: `./gradlew test`

Expected: 150 tests pass (no new tests in this task).

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/arb/ArbModels.kt
git commit -m "arb: add domain types (Arb, ArbOutput, leg types)"
```

---

## Task 4: `eachWayArbMargin` pure math

The closed-form arb math from the spec, as a pure function. TDD with the worked example and edge cases.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt`
- Create: `src/test/kotlin/com/horsey/scraper/arb/EachWayArbMarginTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/arb/EachWayArbMarginTest.kt`:

```kotlin
package com.horsey.scraper.arb

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class EachWayArbMarginTest {

    @Test
    fun `Champ example 11_0 win 1_5 odds 4 places vs BF 10 and 2_5 yields 0_15 margin`() {
        // p=11.0, f=0.2, bw=10.0, bp=2.5
        // L_w = 11/(2*10) = 0.55
        // L_p = (1 + (11-1)*0.2) / (2*2.5) = 3/5 = 0.60
        // margin = 0.55 + 0.60 - 1 = 0.15
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 10.0, bp = 2.5)
        assertEquals(0.15, m, 1e-9)
    }

    @Test
    fun `equilibrium gives margin of zero`() {
        // bw == p and bp == 1 + (p-1)*f → margin == 0
        val p = 7.0
        val f = 0.25
        val bp = 1.0 + (p - 1.0) * f  // 1 + 6*0.25 = 2.5
        val m = eachWayArbMargin(p = p, f = f, bw = p, bp = bp)
        assertTrue(abs(m) < 1e-12, "expected ~0, got $m")
    }

    @Test
    fun `wider Betfair prices give negative margin`() {
        // BF lay prices wider than equilibrium → negative margin (no arb).
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 15.0, bp = 4.0)
        assertTrue(m < 0.0, "expected negative margin, got $m")
    }

    @Test
    fun `bp of 1_0 yields a finite (huge) result, not NaN`() {
        // bp = 1.0 means decimal odds 1.0 (100% probability, never lays).
        // L_p = (1 + (p-1)*f) / (2*1.0) = blow-up
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 10.0, bp = 1.0)
        assertTrue(m.isFinite(), "margin must be finite, got $m")
        assertTrue(m > 0.0, "margin should be very positive, got $m")
    }

    @Test
    fun `1_4 odds 5 places worked example`() {
        // p=6.0 (5/1), f=0.25 (1/4 odds), bw=5.5, bp=2.0
        // L_w = 6/11 = 0.5454545...
        // L_p = (1 + 5*0.25) / (2*2.0) = 2.25/4 = 0.5625
        // margin = 0.5454545... + 0.5625 - 1 = 0.10795454...
        val m = eachWayArbMargin(p = 6.0, f = 0.25, bw = 5.5, bp = 2.0)
        val expected = 6.0 / (2.0 * 5.5) + (1.0 + (6.0 - 1.0) * 0.25) / (2.0 * 2.0) - 1.0
        assertEquals(expected, m, 1e-12)
    }

    @Test
    fun `f of zero collapses to a degenerate case (no place leg payout)`() {
        // L_p = 1 / (2*bp). Margin can still be non-zero but the place
        // leg of the EW pays nothing. The function should still return
        // a finite number — caller is responsible for filtering EW=null.
        val m = eachWayArbMargin(p = 5.0, f = 0.0, bw = 5.0, bp = 2.0)
        assertTrue(m.isFinite())
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.EachWayArbMarginTest'`

Expected: FAIL with `unresolved reference: eachWayArbMargin`.

- [ ] **Step 3: Implement `eachWayArbMargin`**

Create `src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt`:

```kotlin
package com.horsey.scraper.arb

/**
 * Closed-form each-way arbitrage margin per £1 of PaddyPower stake.
 *
 * Given a PaddyPower each-way bet (stake split 50/50 between win and
 * place legs) and Betfair lay prices on the WIN market and the matching
 * TOP_N market, returns the guaranteed profit per £1 PP stake when lay
 * stakes are chosen for equal-profit arb:
 *
 *   L_w    = p / (2·bw)
 *   L_p    = (1 + (p−1)·f) / (2·bp)
 *   margin = L_w + L_p − 1
 *
 * Positive margin = arb. Negative or zero = no arb. The math derivation
 * and a worked example are in the spec at
 * `docs/superpowers/specs/2026-05-14-arb-finder-design.md`.
 *
 * @param p   PaddyPower win decimal odds
 * @param f   each-way fraction in (0, 1] (e.g. 0.2 for 1/5 odds)
 * @param bw  Betfair WIN lay decimal price
 * @param bp  Betfair TOP_N lay decimal price (same N as PP's)
 */
fun eachWayArbMargin(p: Double, f: Double, bw: Double, bp: Double): Double {
    val lw = p / (2.0 * bw)
    val lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.EachWayArbMarginTest'`

Expected: 6 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 156 tests pass (150 baseline + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt \
        src/test/kotlin/com/horsey/scraper/arb/EachWayArbMarginTest.kt
git commit -m "arb: add eachWayArbMargin closed-form calculation"
```

---

## Task 5: `findArbs` orchestrator

The orchestrator joins the two snapshots and produces ranked arbs. TDD against synthetic `ScrapeOutput` + `PaddyOutput` instances.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt`
- Create: `src/test/kotlin/com/horsey/scraper/arb/FindArbsTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/arb/FindArbsTest.kt`:

```kotlin
package com.horsey.scraper.arb

import com.horsey.scraper.MarketType
import com.horsey.scraper.RaceOdds
import com.horsey.scraper.RunnerOdds
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.EachWayTerms
import com.horsey.scraper.paddypower.PaddyOutput
import com.horsey.scraper.paddypower.PaddyRace
import com.horsey.scraper.paddypower.PaddyRunner
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FindArbsTest {

    private val betfairScrapedAt = "2026-05-13T22:00:00Z"
    private val paddyScrapedAt = "2026-05-13T22:00:01Z"

    @Test
    fun `one race, one runner, prices skewed yields one arb`() {
        // Champ example: p=11, f=0.2, bw=10, bp=2.5 → margin 0.15
        val betfair = ScrapeOutput(
            scrapedAt = betfairScrapedAt, raceCount = 1,
            races = listOf(
                raceOdds(
                    raceId = "1.x",
                    runners = listOf(
                        runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5)),
                    ),
                    scrapedMarkets = setOf(MarketType.WIN, MarketType.TOP_4),
                ),
            ),
        )
        val paddy = PaddyOutput(
            scrapedAt = paddyScrapedAt, raceCount = 1,
            races = listOf(
                paddyRace(
                    betfairId = "1.x",
                    runners = listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")),
                    ew = EachWayTerms(0.2, 4),
                ),
            ),
        )
        val arbs = findArbs(betfair, paddy)
        assertEquals(1, arbs.size)
        val arb = arbs.first()
        assertEquals("Champ", arb.runner.name)
        assertEquals(1001L, arb.runner.selectionId)
        assertEquals(0.15, arb.margin, 1e-9)
        assertEquals(MarketType.TOP_4, arb.betfair.topNType)
    }

    @Test
    fun `equilibrium prices yield no arb`() {
        val p = 11.0; val f = 0.2
        val bp = 1.0 + (p - 1.0) * f  // 3.0
        val betfair = ScrapeOutput(
            scrapedAt = betfairScrapedAt, raceCount = 1,
            races = listOf(
                raceOdds(
                    raceId = "1.x",
                    runners = listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to p, MarketType.TOP_4 to bp))),
                    scrapedMarkets = setOf(MarketType.WIN, MarketType.TOP_4),
                ),
            ),
        )
        val paddy = PaddyOutput(
            scrapedAt = paddyScrapedAt, raceCount = 1,
            races = listOf(
                paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, p, "10/1")), EachWayTerms(f, 4)),
            ),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `race in PaddyPower but not Betfair is skipped`() {
        val betfair = ScrapeOutput(betfairScrapedAt, 0, emptyList())
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("X", 1L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `race in Betfair but not PaddyPower is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("X", 1L, mapOf(MarketType.WIN to 5.0, MarketType.TOP_4 to 2.0))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(paddyScrapedAt, 0, emptyList())
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `runner in PaddyPower with no matching selectionId in Betfair is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Other", 999L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `PaddyPower race with null eachWayTerms is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), ew = null)),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `Betfair race missing the matching TOP_N market is skipped`() {
        // PP wants 4 places, BF only scraped WIN + TOP_2.
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_2 to 5.0))),
                setOf(MarketType.WIN, MarketType.TOP_2),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `runner with null lay price on either market is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to null, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `non-runner on PaddyPower side is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x",
                listOf(PaddyRunner(name = "Champ", selectionId = 1001L, winPrice = null, winPriceRaw = null)),
                EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `eachWayTerms_places outside 2 to 5 is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 6))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `multiple positive arbs are sorted by margin descending`() {
        // Race A: margin 0.15 (Champ example).
        // Race B: same setup but bp=2.0 → bigger arb.
        val betfair = ScrapeOutput(
            betfairScrapedAt, 2,
            listOf(
                raceOdds("1.A",
                    listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                    setOf(MarketType.WIN, MarketType.TOP_4)),
                raceOdds("1.B",
                    listOf(runner("Hero", 2002L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.0))),
                    setOf(MarketType.WIN, MarketType.TOP_4)),
            ),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 2,
            listOf(
                paddyRace("1.A", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4)),
                paddyRace("1.B", listOf(paddyRunner("Hero", 2002L, 11.0, "10/1")), EachWayTerms(0.2, 4)),
            ),
        )
        val arbs = findArbs(betfair, paddy)
        assertEquals(2, arbs.size)
        assertTrue(arbs[0].margin > arbs[1].margin, "expected descending margin order: $arbs")
        assertEquals("Hero", arbs[0].runner.name)
    }

    // --- helpers ---

    private fun raceOdds(
        raceId: String,
        runners: List<RunnerOdds>,
        scrapedMarkets: Set<MarketType>,
    ): RaceOdds {
        val msa = linkedMapOf<MarketType, String>()
        for (m in MarketType.values()) if (m in scrapedMarkets) msa[m] = betfairScrapedAt
        return RaceOdds(
            raceId = raceId,
            venue = "Lingfield",
            country = "GB",
            offTime = "2026-05-14T17:40:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$raceId",
            marketName = "17:40 Lingfield",
            marketScrapedAt = msa,
            runners = runners,
        )
    }

    private fun runner(name: String, selectionId: Long, lay: Map<MarketType, Double?>): RunnerOdds =
        RunnerOdds(name = name, lay = lay, selectionId = selectionId)

    private fun paddyRace(
        betfairId: String,
        runners: List<PaddyRunner>,
        ew: EachWayTerms?,
    ): PaddyRace = PaddyRace(
        venue = "Lingfield",
        country = "GB",
        offTime = "2026-05-14T17:40:00+01:00",
        marketName = "17:40 Lingfield",
        raceUrl = "",
        scrapedAt = paddyScrapedAt,
        betfairWinMarketId = betfairId,
        eachWayTerms = ew,
        runners = runners,
    )

    private fun paddyRunner(name: String, selectionId: Long, winPrice: Double, raw: String): PaddyRunner =
        PaddyRunner(name = name, selectionId = selectionId, winPrice = winPrice, winPriceRaw = raw)
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.FindArbsTest'`

Expected: FAIL with `unresolved reference: findArbs`.

- [ ] **Step 3: Implement `findArbs`**

Append to `src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt`:

```kotlin
import com.horsey.scraper.MarketType
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.PaddyOutput

/**
 * Joins a Betfair `ScrapeOutput` with a PaddyPower `PaddyOutput` and
 * computes each-way arbitrage opportunities. See the spec at
 * `docs/superpowers/specs/2026-05-14-arb-finder-design.md` for the
 * normative skip rules and the math.
 *
 * Returns positive-margin opportunities sorted by margin descending.
 * Negative-or-zero-margin (race, runner) tuples are filtered out.
 */
fun findArbs(betfair: ScrapeOutput, paddy: PaddyOutput): List<Arb> {
    val betfairByRaceId = betfair.races.associateBy { it.raceId }
    val out = mutableListOf<Arb>()

    for (paddyRace in paddy.races) {
        val winMarketId = paddyRace.betfairWinMarketId ?: continue
        val betfairRace = betfairByRaceId[winMarketId] ?: continue
        val ew = paddyRace.eachWayTerms ?: continue
        val topNType = topNFromPlaces(ew.places) ?: continue
        if (topNType !in betfairRace.marketScrapedAt.keys) continue

        val betfairBySelectionId = betfairRace.runners
            .mapNotNull { r -> r.selectionId?.let { sel -> sel to r } }
            .toMap()

        for (paddyRunner in paddyRace.runners) {
            val sel = paddyRunner.selectionId ?: continue
            val betfairRunner = betfairBySelectionId[sel] ?: continue
            val ppPrice = paddyRunner.winPrice ?: continue
            val ppRaw = paddyRunner.winPriceRaw ?: continue
            val winLay = betfairRunner.lay[MarketType.WIN] ?: continue
            val topNLay = betfairRunner.lay[topNType] ?: continue

            val margin = eachWayArbMargin(p = ppPrice, f = ew.fraction, bw = winLay, bp = topNLay)
            if (margin <= 0.0) continue

            out += Arb(
                venue = paddyRace.venue,
                country = paddyRace.country,
                offTime = paddyRace.offTime,
                marketName = paddyRace.marketName,
                betfairWinMarketId = winMarketId,
                runner = ArbRunner(name = paddyRunner.name, selectionId = sel),
                paddypower = PaddyPriceLeg(winPrice = ppPrice, winPriceRaw = ppRaw, eachWayTerms = ew),
                betfair = BetfairLayLeg(winLay = winLay, topNLay = topNLay, topNType = topNType),
                margin = margin,
            )
        }
    }
    return out.sortedByDescending { it.margin }
}

private fun topNFromPlaces(n: Int): MarketType? = when (n) {
    2 -> MarketType.TOP_2
    3 -> MarketType.TOP_3
    4 -> MarketType.TOP_4
    5 -> MarketType.TOP_5
    else -> null
}
```

Move the new `import` lines to the existing import block at the top of the file (the file already has `package com.horsey.scraper.arb` from Task 4).

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.FindArbsTest'`

Expected: 11 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 167 tests pass (156 baseline + 11 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/arb/ArbCalculator.kt \
        src/test/kotlin/com/horsey/scraper/arb/FindArbsTest.kt
git commit -m "arb: add findArbs orchestrator with full edge-case handling"
```

---

## Task 6: `ArbSchemaValidator` + `ArbValidateMain`

A standalone validator over an `arbs.json` string, plus a tiny entry-point. Mirrors the existing pattern.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/arb/ArbSchemaValidator.kt`
- Create: `src/main/kotlin/com/horsey/scraper/arb/ArbValidateMain.kt`
- Create: `src/test/kotlin/com/horsey/scraper/arb/ArbSchemaValidatorTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/arb/ArbSchemaValidatorTest.kt`:

```kotlin
package com.horsey.scraper.arb

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ArbSchemaValidatorTest {

    private val happy = """
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
              "runner": { "name": "Champ", "selectionId": 48920004 },
              "paddypower": {
                "winPrice": 11.0, "winPriceRaw": "10/1",
                "eachWayTerms": { "fraction": 0.2, "places": 4 }
              },
              "betfair": { "winLay": 10.0, "topNLay": 2.5, "topNType": "TOP_4" },
              "margin": 0.15
            }
          ]
        }
    """.trimIndent()

    @Test fun `happy path validates`() {
        assertEquals(emptyList(), validateArbsOutput(happy))
    }

    @Test fun `arbCount mismatch is flagged`() {
        val bad = happy.replace("\"arbCount\": 1", "\"arbCount\": 5")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "arbCount" in it && "arbs.length" in it }, errs.toString())
    }

    @Test fun `non-ISO computedAt is flagged`() {
        val bad = happy.replace("2026-05-13T22:35:00.123Z", "yesterday")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "computedAt" in it && "ISO-8601" in it }, errs.toString())
    }

    @Test fun `margin of zero is flagged`() {
        val bad = happy.replace("\"margin\": 0.15", "\"margin\": 0.0")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "margin" in it }, errs.toString())
    }

    @Test fun `margin negative is flagged`() {
        val bad = happy.replace("\"margin\": 0.15", "\"margin\": -0.05")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "margin" in it }, errs.toString())
    }

    @Test fun `unknown topNType is flagged`() {
        val bad = happy.replace("\"topNType\": \"TOP_4\"", "\"topNType\": \"TOP_99\"")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "topNType" in it }, errs.toString())
    }

    @Test fun `EW fraction out of range is flagged`() {
        val bad = happy.replace("\"fraction\": 0.2", "\"fraction\": 1.5")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "fraction" in it }, errs.toString())
    }

    @Test fun `EW places out of range is flagged`() {
        val bad = happy.replace("\"places\": 4", "\"places\": 9")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "places" in it }, errs.toString())
    }

    @Test fun `missing required arb field is flagged`() {
        val bad = happy.replace("\"venue\": \"Clonmel\",", "")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "venue" in it }, errs.toString())
    }

    @Test fun `empty arbs array with zero arbCount validates`() {
        val empty = """
            {
              "computedAt": "2026-05-13T22:35:00Z",
              "betfairScrapedAt": "2026-05-13T22:32:52Z",
              "paddypowerScrapedAt": "2026-05-13T22:32:54Z",
              "arbCount": 0,
              "arbs": []
            }
        """.trimIndent()
        assertEquals(emptyList(), validateArbsOutput(empty))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.ArbSchemaValidatorTest'`

Expected: FAIL with `unresolved reference: validateArbsOutput`.

- [ ] **Step 3: Implement `ArbSchemaValidator.kt`**

Create `src/main/kotlin/com/horsey/scraper/arb/ArbSchemaValidator.kt`:

```kotlin
package com.horsey.scraper.arb

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val EW_PLACES_RANGE = 2..5
private val ALLOWED_TOP_N = setOf("TOP_2", "TOP_3", "TOP_4", "TOP_5")

/**
 * Validates an `arbs.json` payload string against the spec rules.
 * Returns an empty list if valid; otherwise a list of human-readable
 * error descriptions, one per violation.
 */
fun validateArbsOutput(json: String): List<String> {
    val errors = mutableListOf<String>()
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return listOf("not valid JSON object: ${e.message}")
    }

    requireString(root, "computedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "computedAt is not ISO-8601 UTC instant: '$v'"
    }
    requireString(root, "betfairScrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "betfairScrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    requireString(root, "paddypowerScrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "paddypowerScrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    val arbCount = requireInt(root, "arbCount", errors)
    val arbsEl = root.get("arbs")
    if (arbsEl == null || !arbsEl.isJsonArray) {
        errors += "arbs: missing or not array"
        return errors
    }
    val arbs = arbsEl.asJsonArray
    if (arbCount != null && arbCount != arbs.size()) {
        errors += "arbCount ($arbCount) != arbs.length (${arbs.size()})"
    }

    arbs.forEachIndexed { i, arbEl ->
        val ctx = "arbs[$i]"
        if (!arbEl.isJsonObject) { errors += "$ctx: not an object"; return@forEachIndexed }
        val arb = arbEl.asJsonObject

        requireString(arb, "venue", errors)
        requireString(arb, "country", errors)
        requireString(arb, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(arb, "marketName", errors)
        requireString(arb, "betfairWinMarketId", errors)

        val marginEl = arb.get("margin")
        if (marginEl == null || !marginEl.isJsonPrimitive || !marginEl.asJsonPrimitive.isNumber) {
            errors += "$ctx.margin: missing or not a number"
        } else if (marginEl.asDouble <= 0.0) {
            errors += "$ctx.margin must be > 0, got ${marginEl.asDouble}"
        }

        val runnerEl = arb.get("runner")
        if (runnerEl == null || !runnerEl.isJsonObject) {
            errors += "$ctx.runner: missing or not an object"
        } else {
            val runner = runnerEl.asJsonObject
            requireString(runner, "name", errors)
            val selEl = runner.get("selectionId")
            if (selEl == null || !selEl.isJsonPrimitive || !selEl.asJsonPrimitive.isNumber) {
                errors += "$ctx.runner.selectionId: missing or not a number"
            }
        }

        validatePaddyLeg(arb.get("paddypower"), "$ctx.paddypower", errors)
        validateBetfairLeg(arb.get("betfair"), "$ctx.betfair", errors)
    }
    return errors
}

private fun validatePaddyLeg(el: com.google.gson.JsonElement?, ctx: String, errors: MutableList<String>) {
    if (el == null || !el.isJsonObject) {
        errors += "$ctx: missing or not an object"; return
    }
    val pp = el.asJsonObject
    val winPrice = pp.get("winPrice")
    if (winPrice == null || !winPrice.isJsonPrimitive || !winPrice.asJsonPrimitive.isNumber) {
        errors += "$ctx.winPrice: missing or not a number"
    }
    requireString(pp, "winPriceRaw", errors)

    val ewEl = pp.get("eachWayTerms")
    if (ewEl == null || !ewEl.isJsonObject) {
        errors += "$ctx.eachWayTerms: missing or not an object"; return
    }
    val ew = ewEl.asJsonObject
    val frac = ew.get("fraction")?.takeIf { it.isJsonPrimitive }?.asDouble
    if (frac == null || frac <= 0.0 || frac > 1.0) {
        errors += "$ctx.eachWayTerms.fraction must be in (0,1], got $frac"
    }
    val places = ew.get("places")?.takeIf { it.isJsonPrimitive }?.asInt
    if (places == null || places !in EW_PLACES_RANGE) {
        errors += "$ctx.eachWayTerms.places must be in $EW_PLACES_RANGE, got $places"
    }
}

private fun validateBetfairLeg(el: com.google.gson.JsonElement?, ctx: String, errors: MutableList<String>) {
    if (el == null || !el.isJsonObject) {
        errors += "$ctx: missing or not an object"; return
    }
    val bf = el.asJsonObject
    for (key in listOf("winLay", "topNLay")) {
        val v = bf.get(key)
        if (v == null || !v.isJsonPrimitive || !v.asJsonPrimitive.isNumber) {
            errors += "$ctx.$key: missing or not a number"
        }
    }
    val topNType = bf.get("topNType")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
    if (topNType == null) {
        errors += "$ctx.topNType: missing or not a string"
    } else if (topNType !in ALLOWED_TOP_N) {
        errors += "$ctx.topNType: '$topNType' not in $ALLOWED_TOP_N"
    }
}

private fun requireString(
    obj: JsonObject, key: String, errors: MutableList<String>,
    extra: (String) -> Unit = {},
): String? {
    val el = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
        errors += "$key: missing or not string"
        return null
    }
    val v = el.asString
    extra(v)
    return v
}

private fun requireInt(obj: JsonObject, key: String, errors: MutableList<String>): Int? {
    val el = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isNumber) {
        errors += "$key: missing or not number"
        return null
    }
    return el.asInt
}

private fun isIsoUtc(v: String): Boolean = try {
    java.time.Instant.parse(v); true
} catch (e: DateTimeParseException) { false }

private fun isIsoOffsetDateTime(v: String): Boolean = try {
    DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(v); true
} catch (e: DateTimeParseException) { false }
```

- [ ] **Step 4: Implement `ArbValidateMain.kt`**

Create `src/main/kotlin/com/horsey/scraper/arb/ArbValidateMain.kt`:

```kotlin
package com.horsey.scraper.arb

import java.io.File

/**
 * Entry point for ad-hoc validation:
 *   ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=arbs.json
 */
fun main(args: Array<String>) {
    require(args.size == 1) { "usage: ArbValidateMain <path-to-arbs.json>" }
    val path = args[0]
    val errors = validateArbsOutput(File(path).readText())
    if (errors.isEmpty()) {
        println("$path: VALID (matches spec)")
    } else {
        System.err.println("$path: ${errors.size} errors")
        errors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(1)
    }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.ArbSchemaValidatorTest'`

Expected: 10 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: 177 tests pass (167 baseline + 10 new).

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/arb/ArbSchemaValidator.kt \
        src/main/kotlin/com/horsey/scraper/arb/ArbValidateMain.kt \
        src/test/kotlin/com/horsey/scraper/arb/ArbSchemaValidatorTest.kt
git commit -m "arb: add ArbSchemaValidator and ArbValidateMain"
```

---

## Task 7: `ArbMain` CLI

The thin entry point: read input files, validate them via the existing per-source validators, deserialize via Gson into `ScrapeOutput` + `PaddyOutput`, call `findArbs`, package as `ArbOutput`, write `arbs.json`.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/arb/ArbMain.kt`
- Create: `src/test/kotlin/com/horsey/scraper/arb/ArbMainCliTest.kt`

- [ ] **Step 1: Write the failing test (CLI argument parsing)**

Create `src/test/kotlin/com/horsey/scraper/arb/ArbMainCliTest.kt`:

```kotlin
package com.horsey.scraper.arb

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ArbMainCliTest {

    @Test
    fun `zero args yields all defaults`() {
        val paths = parseArbCliArgs(emptyArray())
        assertEquals("betfair.json", paths.betfairInput)
        assertEquals("paddypower.json", paths.paddypowerInput)
        assertEquals("arbs.json", paths.output)
    }

    @Test
    fun `three args explicit`() {
        val paths = parseArbCliArgs(arrayOf("a.json", "b.json", "c.json"))
        assertEquals("a.json", paths.betfairInput)
        assertEquals("b.json", paths.paddypowerInput)
        assertEquals("c.json", paths.output)
    }

    @Test
    fun `one arg rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a.json")) }
    }

    @Test
    fun `two args rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a.json", "b.json")) }
    }

    @Test
    fun `four args rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a", "b", "c", "d")) }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.ArbMainCliTest'`

Expected: FAIL with `unresolved reference: parseArbCliArgs`.

- [ ] **Step 3: Implement `ArbMain.kt`**

Create `src/main/kotlin/com/horsey/scraper/arb/ArbMain.kt`:

```kotlin
package com.horsey.scraper.arb

import com.google.gson.GsonBuilder
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.PaddyOutput
import com.horsey.scraper.paddypower.validatePaddyOutput
import com.horsey.scraper.validateScrapeOutput
import java.io.File
import java.time.Instant

data class ArbCliPaths(
    val betfairInput: String,
    val paddypowerInput: String,
    val output: String,
)

/**
 * Two CLI modes only:
 *   - 0 args: defaults (betfair.json, paddypower.json, arbs.json in cwd).
 *   - 3 args: explicit paths in the order betfair-in, paddy-in, output.
 * Anything else throws `IllegalArgumentException` so the caller can
 * surface a clean usage message and exit non-zero.
 */
fun parseArbCliArgs(args: Array<String>): ArbCliPaths = when (args.size) {
    0 -> ArbCliPaths("betfair.json", "paddypower.json", "arbs.json")
    3 -> ArbCliPaths(args[0], args[1], args[2])
    else -> throw IllegalArgumentException(
        "usage: ArbMain                                          # all defaults\n" +
        "       ArbMain <betfair-in> <paddypower-in> <arbs-out>  # all explicit"
    )
}

/**
 * Entry point. Reads the two snapshot files, validates each against
 * its own schema, computes arbs, writes `arbs.json`.
 *
 * Exit codes:
 *   - 0: ran cleanly (even if zero arbs).
 *   - 1: bad CLI usage.
 *   - 2: input file missing, unparseable, or fails its schema validator.
 */
fun main(args: Array<String>) {
    val paths = try {
        parseArbCliArgs(args)
    } catch (e: IllegalArgumentException) {
        System.err.println(e.message)
        kotlin.system.exitProcess(1)
    }

    val betfairText = readOrExit(paths.betfairInput)
    val paddyText = readOrExit(paths.paddypowerInput)

    val betfairErrors = validateScrapeOutput(betfairText)
    if (betfairErrors.isNotEmpty()) {
        System.err.println("Error: ${paths.betfairInput} fails Betfair schema:")
        betfairErrors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(2)
    }
    val paddyErrors = validatePaddyOutput(paddyText)
    if (paddyErrors.isNotEmpty()) {
        System.err.println("Error: ${paths.paddypowerInput} fails PaddyPower schema:")
        paddyErrors.forEach { System.err.println("  - $it") }
        kotlin.system.exitProcess(2)
    }

    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()
    val betfair = try {
        gson.fromJson(betfairText, ScrapeOutput::class.java)
    } catch (e: Exception) {
        System.err.println("Error: ${paths.betfairInput} could not be deserialised: ${e.message}")
        kotlin.system.exitProcess(2)
    }
    val paddy = try {
        gson.fromJson(paddyText, PaddyOutput::class.java)
    } catch (e: Exception) {
        System.err.println("Error: ${paths.paddypowerInput} could not be deserialised: ${e.message}")
        kotlin.system.exitProcess(2)
    }

    val computedAt = Instant.now().toString()
    val arbs = findArbs(betfair, paddy)
    val output = ArbOutput(
        computedAt = computedAt,
        betfairScrapedAt = betfair.scrapedAt,
        paddypowerScrapedAt = paddy.scrapedAt,
        arbCount = arbs.size,
        arbs = arbs,
    )
    File(paths.output).writeText(gson.toJson(output))
    println("Wrote ${paths.output} (${arbs.size} arbs from ${betfair.races.size} BF races and ${paddy.races.size} PP races)")
}

private fun readOrExit(path: String): String {
    val f = File(path)
    if (!f.exists()) {
        System.err.println("Error: input file not found: $path")
        kotlin.system.exitProcess(2)
    }
    return try {
        f.readText()
    } catch (e: Exception) {
        System.err.println("Error: failed to read $path: ${e.message}")
        kotlin.system.exitProcess(2)
    }
}
```

- [ ] **Step 4: Run new tests, verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.arb.ArbMainCliTest'`

Expected: 5 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 182 tests pass (177 baseline + 5 new).

- [ ] **Step 6: Verify the entry-point loads via Gradle**

Run: `./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt --args="missing.json missing2.json out.json" 2>&1 | head -3`

Expected: stderr contains `Error: input file not found: missing.json` and the process exits non-zero. The point is that the main class loads cleanly.

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/arb/ArbMain.kt \
        src/test/kotlin/com/horsey/scraper/arb/ArbMainCliTest.kt
git commit -m "arb: add ArbMain CLI (reads two snapshots, writes arbs.json)"
```

---

## Task 8: Wire `ArbMain` into `run.sh`

After the existing scrapers complete, run the arb finder against the just-written files.

**Files:**
- Modify: `run.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Inspect current `run.sh`**

Run: `cat run.sh`

Expected: a single `exec ./gradlew run --quiet --args="${1:-gb-ie}"` line (the existing scraper invocation).

- [ ] **Step 2: Replace `run.sh`**

Replace the entire contents of `run.sh` with:

```bash
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
```

- [ ] **Step 3: Verify the script syntax**

Run: `bash -n run.sh`

Expected: no output, exit code 0.

- [ ] **Step 4: Verify the executable bit**

Run: `ls -l run.sh`

Expected: mode column shows `x` for the user. If not, `chmod +x run.sh`.

- [ ] **Step 5: Add `arbs.json` to `.gitignore`**

Open `.gitignore`. Find the existing scraper-output block:

```
# Local scraper output
scraper.log
betfair.json
paddypower.json
debug-page.html
```

Add `arbs.json` so it becomes:

```
# Local scraper output
scraper.log
betfair.json
paddypower.json
arbs.json
debug-page.html
```

- [ ] **Step 6: Commit**

```bash
git add run.sh .gitignore
git commit -m "run.sh: chain ArbMain after scrapers; gitignore arbs.json"
```

---

## Task 9: Final validation

Verification only — no code changes, no commits.

- [ ] **Step 1: Full test run**

Run: `./gradlew test 2>&1 | tail -10`

Expected: `BUILD SUCCESSFUL`. Test total approximately 182.

- [ ] **Step 2: Compile + assemble**

Run: `./gradlew compileKotlin compileTestKotlin assemble`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: ArbMain entry-point loads**

Run: `./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt --args="nonexistent.json nonexistent2.json out.json" 2>&1 | head -3`

Expected: stderr contains `Error: input file not found: nonexistent.json`.

- [ ] **Step 4: ArbValidateMain entry-point loads**

Run: `./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=missing.json 2>&1 | head -3`

Expected: some kind of "file not found" exception — main class loads cleanly.

- [ ] **Step 5: Commits added by this plan**

Run: `git log --oneline master..HEAD`

(Base is `master`.) Expected: nine commits, one per task.

- [ ] **Step 6: Surface the live-smoke step to the user**

Don't run a live scrape — it requires Betfair credentials and the Playwright browser bootstrap. Tell the user:

> "Arb finder ready. To smoke-test live, run `./run.sh`. Expected output: produces `betfair.json`, `paddypower.json`, and `arbs.json`. Validate the arbs file with `./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=arbs.json`. Expected: `arbs.json: VALID (matches spec)`. The number of arbs depends on whether today's prices skew across the two books."

No commit in this task.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **The static site itself.** This plan produces `arbs.json`; rendering it is its own project.
- **Commission accounting.** Margin is the raw mathematical surplus. Static site or future config can subtract Betfair's 5%.
- **Bankroll-scaled stake outputs.** Margin is per £1; the static site multiplies by whatever bankroll it cares to display.
- **Liquidity-aware arbs.** The current calculation ignores `availableToLay[0].size`. A 50% margin on a £2 lay is irrelevant; a future enhancement could weight by available size.
- **Continuous monitoring / re-running on price ticks.** v1 is a one-shot snapshot calculator.
- **Historical arb archive.** No persistence beyond the current `arbs.json`.
- **More bookmakers, multi-way arbs.** v1 is two-way (PP back vs BF lay) only.
