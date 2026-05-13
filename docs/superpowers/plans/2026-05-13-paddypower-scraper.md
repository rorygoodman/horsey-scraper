# PaddyPower Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-shot PaddyPower next-races scraper that writes a `paddypower.json` snapshot (horse names, decimal+fractional win prices, per-race each-way terms) alongside the existing Betfair `data.json`. First of N bookmaker scrapers.

**Architecture:** New sub-package `com.horsey.scraper.paddypower`. Hand-rolled HTTP via `java.net.http.HttpClient` against PaddyPower's internal JSON endpoint (discovered in Task 0). Pure parsers convert the response into domain types, region filter drops out-of-scope races, schema validator enforces the output contract. Runs from `Main.kt` after the Betfair pipeline.

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`, Gson, `java.net.http.HttpClient` from the JDK. No new Maven dependencies.

**Spec:** `docs/superpowers/specs/2026-05-13-paddypower-scraper-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- This is a Kotlin/JVM one-shot CLI that already produces `data.json` from the Betfair Exchange API. You're adding a second output, `paddypower.json`, from PaddyPower's public next-races view.
- Output shape is fixed by the spec — read the spec before starting. `paddypower.json` is independent of `data.json`; the two files are joined later by a separate (out-of-scope) arb-finder.
- The Betfair-side code lives directly under `src/main/kotlin/com/horsey/scraper/`. PaddyPower code lives in a *sub-package* `src/main/kotlin/com/horsey/scraper/paddypower/`. Same for tests.
- Don't touch any Betfair-side code except `Main.kt` (Task 9 appends one block to it).
- TDD throughout: every behaviour gets a failing test before the implementation.
- Test baseline at the start of Task 1: 95 tests (verify with `./gradlew test`). Each task that adds tests will state the expected new count.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

### The endpoint-discovery gotcha

PaddyPower's site is a thin JS shell — the price data isn't in the initial HTML. We need to hit the internal JSON endpoint that the frontend calls. That endpoint isn't documented and may change over time. **Task 0** captures a real response as a fixture and pins the URL. Every subsequent parser task is grounded in that fixture, not in guesses.

If Task 0 cannot find a JSON endpoint (e.g. PaddyPower delivers data over WebSocket or as inlined SSR JSON only), STOP and surface this to the user — the spec's documented fallback is Playwright, which is a different implementation path not covered by this plan.

### About the test fixture

The fixture at `src/test/resources/paddy-next-races-sample.json` is the contract. Tasks 4, 6, and 9 reference it. You may add small synthetic JSON snippets in test files for focused edge cases (e.g. "race with no country"), but the canonical happy-path test uses the real fixture.

---

## Task 0: Discover the endpoint and capture the fixture

**Required outputs (committed):**
- `src/test/resources/paddy-next-races-sample.json` — a real response body from PaddyPower's next-races JSON endpoint.
- `src/test/resources/paddy-next-races-endpoint.txt` — a 4-line file listing the endpoint URL, HTTP method, any required headers (e.g. cookies, custom `X-*`), and the date captured.

**This task is human-blocking.** A subagent should *attempt* the discovery via WebFetch first; if WebFetch can't find the endpoint, report **BLOCKED** with a clear message so the human partner can do the DevTools work.

- [ ] **Step 1: Attempt automated discovery via WebFetch**

Fetch `https://www.paddypower.com/horse-racing` and look in the response for clues:
- Inline `<script>` tags containing URLs matching patterns like `/api/`, `/cms/`, `/sports/`, `/odds/`, or containing the strings `nextRaces`, `meetings`, or `horse-racing` and `.json`.
- Any global config object (e.g. `window.__INITIAL_STATE__`) that lists API base URLs.
- Open Graph / meta tags referencing API hosts.

Report what you find. If you locate a plausible endpoint URL, proceed to Step 2. If not, report BLOCKED with what you searched for and a suggested DevTools recipe for the human.

- [ ] **Step 2: Validate the endpoint with a real request**

If Step 1 surfaced a candidate URL, fetch it with `curl -s -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' '<URL>' > /tmp/paddy-probe.json` (no auth needed; PP's next-races view is public).

Verify the response is JSON and contains race/runner data (look for venue strings, time strings, price strings). If yes, proceed. If you get HTML, an error page, or a non-race JSON shape, the URL is wrong — return to Step 1 or BLOCK.

- [ ] **Step 3: Commit the fixture and endpoint metadata**

Move the validated response to the fixture location and write the metadata file:

```bash
mkdir -p src/test/resources
mv /tmp/paddy-probe.json src/test/resources/paddy-next-races-sample.json
```

Create `src/test/resources/paddy-next-races-endpoint.txt` with this exact format (replace bracketed values):

```
URL: [the full endpoint URL]
Method: [GET or POST]
Headers: [comma-separated list of required headers beyond User-Agent, or "none"]
Captured: [today's date, YYYY-MM-DD]
```

- [ ] **Step 4: Commit**

```bash
git add src/test/resources/paddy-next-races-sample.json src/test/resources/paddy-next-races-endpoint.txt
git commit -m "paddy: capture next-races endpoint fixture for TDD"
```

**If you're blocked at Step 1 or 2:** report BLOCKED with the specific DevTools recipe for the human:

> 1. Open https://www.paddypower.com/horse-racing in Chrome.
> 2. F12 → Network tab → filter "XHR/Fetch".
> 3. Refresh the page.
> 4. Sort by Size (descending). Look for a response that's JSON and contains race data (venue + horse names).
> 5. Right-click → "Save response as..." → save to `src/test/resources/paddy-next-races-sample.json`.
> 6. Right-click → "Copy as cURL" → record the URL, method, and any headers in `src/test/resources/paddy-next-races-endpoint.txt`.
> 7. Commit both files with `git commit -m "paddy: capture next-races endpoint fixture for TDD"`.

---

## Task 1: `PaddyModels.kt` — domain types

Create the data classes. No tests — Kotlin's `data class` equality/`toString`/`copy` are compiler-generated and trivially correct.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyModels.kt`

- [ ] **Step 1: Create the file**

```kotlin
package com.horsey.scraper.paddypower

/**
 * Each-way terms attached to a single race. `fraction` is the place-price
 * fraction in (0, 1] (e.g. `0.2` for "1/5 odds"); `places` is the number
 * of paid places in 1..6.
 */
data class EachWayTerms(
    val fraction: Double,
    val places: Int,
)

/**
 * One runner on a PaddyPower race. `winPrice` and `winPriceRaw` are both
 * null or both populated (parity enforced by the schema validator). Null
 * means a non-runner or a price the parser could not interpret.
 */
data class PaddyRunner(
    val name: String,
    val winPrice: Double?,
    val winPriceRaw: String?,
)

/**
 * One race as observed on PaddyPower's next-races view. `offTime` is an
 * ISO-8601 string with Europe/London offset, formatted identically to
 * the Betfair side's `offTime` so a string compare suffices as a join
 * key. `country` is ISO 3166-1 alpha-2.
 */
data class PaddyRace(
    val venue: String,
    val country: String,
    val offTime: String,
    val marketName: String,
    val raceUrl: String,
    val scrapedAt: String,
    val eachWayTerms: EachWayTerms?,
    val runners: List<PaddyRunner>,
)

/** Top-level wrapper for `paddypower.json`. */
data class PaddyOutput(
    val scrapedAt: String,
    val raceCount: Int,
    val races: List<PaddyRace>,
)
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Run full suite**

Run: `./gradlew test`

Expected: 95 tests pass (no new tests).

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyModels.kt
git commit -m "paddy: add domain types (PaddyRace, PaddyRunner, EachWayTerms, PaddyOutput)"
```

---

## Task 2: `fractionalToDecimal` — fraction → decimal odds

Pure parser. TDD.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/FractionToDecimalTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/paddypower/FractionToDecimalTest.kt`:

```kotlin
package com.horsey.scraper.paddypower

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class FractionToDecimalTest {
    @Test fun `simple fraction 5_2 is 3_5`()  = assertEquals(3.5, fractionalToDecimal("5/2"))
    @Test fun `9_2 is 5_5`()                   = assertEquals(5.5, fractionalToDecimal("9/2"))
    @Test fun `11_4 is 3_75`()                 = assertEquals(3.75, fractionalToDecimal("11/4"))
    @Test fun `1_1 is 2_0`()                   = assertEquals(2.0, fractionalToDecimal("1/1"))
    @Test fun `1_100 is 1_01`()                = assertEquals(1.01, fractionalToDecimal("1/100"))

    @Test fun `evens word form lowercase`()    = assertEquals(2.0, fractionalToDecimal("evens"))
    @Test fun `EVS abbreviation uppercase`()   = assertEquals(2.0, fractionalToDecimal("EVS"))
    @Test fun `Evens mixed case`()             = assertEquals(2.0, fractionalToDecimal("Evens"))
    @Test fun `whitespace-padded fraction`()   = assertEquals(3.5, fractionalToDecimal(" 5/2 "))

    @Test fun `SP returns null`()              = assertNull(fractionalToDecimal("SP"))
    @Test fun `empty string returns null`()    = assertNull(fractionalToDecimal(""))
    @Test fun `garbage returns null`()         = assertNull(fractionalToDecimal("abc"))
    @Test fun `bare slash returns null`()      = assertNull(fractionalToDecimal("/"))
    @Test fun `divide by zero returns null`()  = assertNull(fractionalToDecimal("5/0"))
    @Test fun `negative numerator returns null`() = assertNull(fractionalToDecimal("-1/2"))
    @Test fun `non-integer fraction returns null`() = assertNull(fractionalToDecimal("1.5/2"))
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.FractionToDecimalTest'`

Expected: FAIL with `unresolved reference: fractionalToDecimal`.

- [ ] **Step 3: Implement `fractionalToDecimal`**

Create `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`:

```kotlin
package com.horsey.scraper.paddypower

private val FRACTION_REGEX = Regex("""^(\d+)/(\d+)$""")
private val EVENS_FORMS = setOf("evens", "evs", "even")

/**
 * Converts a PaddyPower price string into decimal odds.
 *
 * Accepts simple integer fractions (`"5/2"` → `3.5`) and the "evens"
 * word forms (`"evens"`, `"EVS"`, `"Evens"` → `2.0`). Returns null for
 * `"SP"`, empty strings, whitespace-only, divide-by-zero, negatives,
 * non-integer fractions, or anything else that isn't a recognised
 * fractional odds string.
 *
 * Decimal odds = 1 + numerator/denominator.
 */
fun fractionalToDecimal(raw: String): Double? {
    val s = raw.trim()
    if (s.isEmpty()) return null
    if (s.lowercase() in EVENS_FORMS) return 2.0
    val m = FRACTION_REGEX.matchEntire(s) ?: return null
    val num = m.groupValues[1].toInt()
    val den = m.groupValues[2].toInt()
    if (den == 0) return null
    return 1.0 + num.toDouble() / den.toDouble()
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.FractionToDecimalTest'`

Expected: 17 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 112 tests pass (95 baseline + 17 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt src/test/kotlin/com/horsey/scraper/paddypower/FractionToDecimalTest.kt
git commit -m "paddy: add fractionalToDecimal price converter"
```

---

## Task 3: `parseEachWayTerms` — text → `EachWayTerms?`

Pure parser. TDD.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/EachWayTermsParserTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/paddypower/EachWayTermsParserTest.kt`:

```kotlin
package com.horsey.scraper.paddypower

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class EachWayTermsParserTest {
    @Test fun `standard PaddyPower format`() {
        assertEquals(EachWayTerms(0.2, 3), parseEachWayTerms("1/5 Odds, 3 Places"))
    }

    @Test fun `1_4 odds 4 places`() {
        assertEquals(EachWayTerms(0.25, 4), parseEachWayTerms("1/4 Odds, 4 Places"))
    }

    @Test fun `case insensitive`() {
        assertEquals(EachWayTerms(0.2, 3), parseEachWayTerms("1/5 odds, 3 places"))
        assertEquals(EachWayTerms(0.25, 4), parseEachWayTerms("1/4 ODDS, 4 PLACES"))
    }

    @Test fun `alternate place-list form`() {
        // "1/5 odds 1,2,3" — three places listed
        assertEquals(EachWayTerms(0.2, 3), parseEachWayTerms("1/5 odds 1,2,3"))
    }

    @Test fun `alternate place-list form four places`() {
        assertEquals(EachWayTerms(0.25, 4), parseEachWayTerms("1/4 odds 1,2,3,4"))
    }

    @Test fun `with Each Way prefix`() {
        assertEquals(EachWayTerms(0.2, 3), parseEachWayTerms("Each Way: 1/5 Odds, 3 Places"))
    }

    @Test fun `whitespace-padded`() {
        assertEquals(EachWayTerms(0.2, 3), parseEachWayTerms("  1/5 Odds, 3 Places  "))
    }

    @Test fun `empty string returns null`() {
        assertNull(parseEachWayTerms(""))
    }

    @Test fun `unrecognised text returns null`() {
        assertNull(parseEachWayTerms("Place market not available"))
    }

    @Test fun `fraction without places returns null`() {
        assertNull(parseEachWayTerms("1/5 Odds"))
    }

    @Test fun `places without fraction returns null`() {
        assertNull(parseEachWayTerms("3 Places"))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.EachWayTermsParserTest'`

Expected: FAIL with `unresolved reference: parseEachWayTerms`.

- [ ] **Step 3: Implement `parseEachWayTerms`**

Append to `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`:

```kotlin
// Matches either "N/D odds … P places" or "N/D odds A,B,C..." where the
// place count is either the explicit "P places" number or the count of
// comma-separated positions.
private val EW_FRACTION = Regex("""(\d+)\s*/\s*(\d+)\s*odds""", RegexOption.IGNORE_CASE)
private val EW_PLACES_EXPLICIT = Regex("""(\d+)\s*places?""", RegexOption.IGNORE_CASE)
private val EW_PLACES_LIST = Regex("""odds\s+((?:\d+\s*,\s*)+\d+)""", RegexOption.IGNORE_CASE)

/**
 * Parses an each-way-terms description string into [EachWayTerms].
 *
 * Accepts PaddyPower's common forms:
 *   - `"1/5 Odds, 3 Places"` → `EachWayTerms(0.2, 3)`
 *   - `"1/4 Odds, 4 Places"` → `EachWayTerms(0.25, 4)`
 *   - `"1/5 odds 1,2,3"`     → `EachWayTerms(0.2, 3)` (places counted from the list)
 *   - `"Each Way: 1/5 Odds, 3 Places"` (with prefix)
 *
 * Returns null when either the fraction or the place count is missing or
 * unparseable. Case-insensitive, whitespace-tolerant.
 */
fun parseEachWayTerms(raw: String): EachWayTerms? {
    val s = raw.trim()
    if (s.isEmpty()) return null

    val fracMatch = EW_FRACTION.find(s) ?: return null
    val num = fracMatch.groupValues[1].toIntOrNull() ?: return null
    val den = fracMatch.groupValues[2].toIntOrNull() ?: return null
    if (den == 0) return null
    val fraction = num.toDouble() / den.toDouble()

    val places: Int = EW_PLACES_EXPLICIT.find(s)?.groupValues?.get(1)?.toIntOrNull()
        ?: EW_PLACES_LIST.find(s)?.groupValues?.get(1)
            ?.split(",")?.map { it.trim() }?.count { it.toIntOrNull() != null }
        ?: return null
    if (places <= 0) return null

    return EachWayTerms(fraction, places)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.EachWayTermsParserTest'`

Expected: 11 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 123 tests pass (112 + 11 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt src/test/kotlin/com/horsey/scraper/paddypower/EachWayTermsParserTest.kt
git commit -m "paddy: add parseEachWayTerms"
```

---

## Task 4: `parsePaddyNextRaces` — JSON → `List<PaddyRace>`

The behavioural contract is fixed by the spec. The exact JSON shape (key names, nesting) depends on what Task 0 captured. **Read `src/test/resources/paddy-next-races-sample.json` first to understand the shape**, then write the parser against it.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt`

- [ ] **Step 1: Inspect the fixture**

Read `src/test/resources/paddy-next-races-sample.json` (committed in Task 0). Note:
- Where the race array lives (top-level or under a key like `data`, `races`, `meetings`, etc.).
- The race-object key names for: venue, country (or country code, or country name), start time, race URL/path, each-way terms.
- The runner key names for: horse name, win price (and whether it's a string `"9/2"` or already decimal, or both).
- How non-runners are marked.

Write a short note in the test file's class-level KDoc summarising the shape so future maintainers don't have to re-derive it.

- [ ] **Step 2: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt` with the **behavioural** tests below. Build per-test JSON snippets that match the real fixture's shape (use Read to confirm field names, then construct minimal raw strings). The full-fixture happy-path test reads the fixture from disk.

```kotlin
package com.horsey.scraper.paddypower

import java.nio.file.Files
import java.nio.file.Paths
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Tests for parsePaddyNextRaces.
 *
 * The exact JSON shape of PaddyPower's next-races response is captured in
 * `src/test/resources/paddy-next-races-sample.json`. See the metadata at
 * `src/test/resources/paddy-next-races-endpoint.txt` for the URL/method
 * this fixture was captured from.
 *
 * The happy-path test parses the real fixture end-to-end. Other tests use
 * synthetic JSON snippets that mirror the fixture's shape but trim away
 * everything irrelevant to the behaviour under test.
 */
class PaddyResponsesTest {

    private val fixedNow = Instant.parse("2026-05-13T12:00:00Z")
    private val nowProvider = { fixedNow }

    @Test
    fun `parses the real fixture into at least one race`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        assertTrue(races.isNotEmpty(), "fixture should contain at least one race")
        val first = races.first()
        assertTrue(first.venue.isNotBlank(), "venue must be populated")
        assertTrue(first.country.isNotBlank(), "country must be populated")
        assertTrue(first.offTime.matches(Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z""")),
            "offTime must be ISO-8601 with offset, got '${first.offTime}'")
        assertEquals(fixedNow.toString(), first.scrapedAt,
            "each race's scrapedAt comes from the injected nowProvider")
        assertTrue(first.runners.isNotEmpty(), "race must have at least one runner")
    }

    @Test
    fun `non-runners have null prices but stay in the runner list`() {
        // The synth helper builds a race fixture containing exactly one
        // non-runner (marker discovered by inspecting the real fixture for
        // any race with one — absent price field, status flag, etc.) and at
        // least one normal runner.
        val json = synthRaceWithRunners(runnersJson = synthRunnersWithNonRunner())
        val race = parsePaddyNextRaces(json, nowProvider).single()
        val nonRunner = race.runners.first { it.winPrice == null }
        assertNull(nonRunner.winPriceRaw, "non-runner has both price fields null")
        assertTrue(race.runners.size >= 2, "non-runner is preserved in the list, not dropped")
    }

    @Test
    fun `race without country is dropped`() {
        val json = synthRaceWithoutCountry()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `race with zero parseable runners is dropped`() {
        val json = synthRaceWithEmptyRunners()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `each-way terms are populated when PaddyPower offers them`() {
        val json = synthRaceWithEachWay("1/5 Odds, 3 Places")
        val race = parsePaddyNextRaces(json, nowProvider).single()
        assertEquals(EachWayTerms(0.2, 3), race.eachWayTerms)
    }

    @Test
    fun `each-way terms are null when PaddyPower omits them`() {
        val json = synthRaceWithoutEachWay()
        val race = parsePaddyNextRaces(json, nowProvider).single()
        assertNull(race.eachWayTerms)
    }

    @Test
    fun `winPrice is decimal and winPriceRaw is the original fraction`() {
        val json = synthRaceWithPrice(rawPrice = "9/2")
        val race = parsePaddyNextRaces(json, nowProvider).single()
        val r = race.runners.first()
        assertEquals(5.5, r.winPrice)
        assertEquals("9/2", r.winPriceRaw)
    }

    @Test
    fun `marketName combines HH_mm and venue`() {
        val json = synthRaceWithVenueAndOffTime("Lingfield", "2026-05-09T13:30:00+01:00")
        val race = parsePaddyNextRaces(json, nowProvider).single()
        assertEquals("13:30 Lingfield", race.marketName)
    }

    @Test
    fun `each race carries the injected scrapedAt`() {
        val json = synthRaceWithRunners(synthRunnersWithNonRunner())
        val race = parsePaddyNextRaces(json, nowProvider).single()
        assertEquals(fixedNow.toString(), race.scrapedAt)
        // And it's distinct from offTime's representation:
        assertNotEquals(race.scrapedAt, race.offTime)
    }

    // --- Synthetic fixture builders ---
    //
    // Replace the bodies below with minimal JSON strings that match the
    // shape you observed in `paddy-next-races-sample.json`. Each builder
    // should produce just enough JSON to exercise the test in question.
    //
    // Example skeleton (adjust field names to match the fixture):
    //
    //   private fun synthRaceWithEachWay(terms: String): String = """
    //       { "races": [
    //           { "venue": "Bath", "country": "GB",
    //             "startTime": "2026-05-13T19:12:00Z",
    //             "eachWayTerms": "$terms",
    //             "raceUrl": "/horse-racing/bath/19-12",
    //             "runners": [ { "name": "Man Is King", "price": "5/2" } ]
    //           }
    //         ] }
    //   """.trimIndent()

    private fun synthRunnersWithNonRunner(): String =
        error("Step 4: replace body with a runners-array JSON snippet containing one non-runner and one normal runner, matching the fixture's runner shape.")
    private fun synthRaceWithRunners(runnersJson: String): String =
        error("Step 4: replace body with a one-race JSON snippet whose runners array is `$runnersJson`, matching the fixture's race shape.")
    private fun synthRaceWithoutCountry(): String =
        error("Step 4: replace body with a one-race JSON snippet that has every required field except country (or with country empty).")
    private fun synthRaceWithEmptyRunners(): String =
        error("Step 4: replace body with a one-race JSON snippet whose runners array is empty.")
    private fun synthRaceWithEachWay(terms: String): String =
        error("Step 4: replace body with a one-race JSON snippet whose each-way-terms field is `$terms`.")
    private fun synthRaceWithoutEachWay(): String =
        error("Step 4: replace body with a one-race JSON snippet that omits or nulls the each-way-terms field.")
    private fun synthRaceWithPrice(rawPrice: String): String =
        error("Step 4: replace body with a one-race JSON snippet whose single runner has price `$rawPrice`.")
    private fun synthRaceWithVenueAndOffTime(venue: String, offTime: String): String =
        error("Step 4: replace body with a one-race JSON snippet whose venue is `$venue` and start time matches `$offTime`.")
}
```

The `error(...)` calls in the synth builders will throw `IllegalStateException` at runtime — that's intentional, so the tests fail loudly until you replace them with concrete fixture-shaped JSON in Step 4 alongside the parser implementation.

- [ ] **Step 3: Implement `parsePaddyNextRaces`**

Append to `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`:

```kotlin
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val LONDON = ZoneId.of("Europe/London")
private val HHMM = DateTimeFormatter.ofPattern("HH:mm")

/**
 * Shreds a PaddyPower next-races JSON response into [PaddyRace] objects.
 *
 * The exact JSON shape is fixture-dependent — see
 * `src/test/resources/paddy-next-races-sample.json` and the test class
 * KDoc on `PaddyResponsesTest` for a description of the fields used.
 *
 * Drops races that:
 *  - have no parseable country (the region filter would be unsafe)
 *  - have zero parseable runners (no usable signal)
 *
 * Non-runners are preserved in the runner list with both price fields
 * null. Each race carries the [nowProvider]'s timestamp as `scrapedAt`.
 * Caller is responsible for the top-level `PaddyOutput.scrapedAt`.
 */
fun parsePaddyNextRaces(
    json: String,
    nowProvider: () -> Instant = { Instant.now() },
): List<PaddyRace> {
    val root = JsonParser.parseString(json)
    // Locate the race array — this depends on the fixture shape.
    // E.g. for `{ "races": [...] }`: `root.asJsonObject.getAsJsonArray("races")`.
    // For `{ "data": { "meetings": [...] } }`: navigate down accordingly.
    // For a top-level array: `root.asJsonArray`.
    val arr = locateRaceArray(root)
    val nowStr = nowProvider().toString()
    val out = mutableListOf<PaddyRace>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val race = paddyRaceFromJson(el.asJsonObject, nowStr) ?: continue
        out += race
    }
    return out
}

/**
 * Locates the array of races inside the JSON root. The navigation path
 * is fixture-dependent — adjust this single function to match the key
 * path observed in `src/test/resources/paddy-next-races-sample.json`.
 *
 * Examples:
 *   - top-level array (`[...]`)                 → `root.asJsonArray`
 *   - `{ "races": [...] }`                      → `root.asJsonObject.getAsJsonArray("races")`
 *   - `{ "data": { "meetings": [...] } }`       → navigate via `data` then `meetings`
 *
 * The default below assumes `{ "races": [...] }`. Replace if the fixture
 * shows otherwise.
 */
private fun locateRaceArray(root: com.google.gson.JsonElement): com.google.gson.JsonArray {
    return root.asJsonObject.getAsJsonArray("races")
}

/**
 * Field-key map. All JSON-shape-dependent string constants live here so
 * a single edit suffices when adapting to the fixture. Adjust each value
 * to match the key actually used in
 * `src/test/resources/paddy-next-races-sample.json`. The defaults below
 * are a starting guess; rename to match what's in the fixture.
 */
private object Field {
    const val VENUE        = "venue"
    const val COUNTRY      = "country"
    const val START_TIME   = "startTime"
    const val RACE_URL     = "raceUrl"
    const val EW_TERMS     = "eachWayTerms"
    const val RUNNERS      = "runners"
    const val RUNNER_NAME  = "name"
    const val RUNNER_PRICE = "price"
}

/**
 * Builds a single [PaddyRace] from one race-object in the JSON. Returns
 * null if any required field is missing or unparseable.
 */
private fun paddyRaceFromJson(root: JsonObject, scrapedAt: String): PaddyRace? {
    val venue = root.get(Field.VENUE)?.takeIf { it.isJsonPrimitive }?.asString ?: return null
    val country = root.get(Field.COUNTRY)?.takeIf { it.isJsonPrimitive }?.asString?.takeIf { it.isNotBlank() } ?: run {
        System.err.println("paddy: dropping race with no country at venue=$venue")
        return null
    }
    val startTimeRaw = root.get(Field.START_TIME)?.takeIf { it.isJsonPrimitive }?.asString ?: return null
    val offTime = utcOrIsoToLondon(startTimeRaw) ?: return null
    val raceUrl = root.get(Field.RACE_URL)?.takeIf { it.isJsonPrimitive }?.asString ?: ""

    val runners = (root.get(Field.RUNNERS)?.takeIf { it.isJsonArray }?.asJsonArray ?: return null)
        .mapNotNull { rEl ->
            if (!rEl.isJsonObject) return@mapNotNull null
            val r = rEl.asJsonObject
            val name = r.get(Field.RUNNER_NAME)?.takeIf { it.isJsonPrimitive }?.asString ?: return@mapNotNull null
            val priceRaw = r.get(Field.RUNNER_PRICE)?.takeIf { it.isJsonPrimitive }?.asString
            val priceDecimal = priceRaw?.let { fractionalToDecimal(it) }
            // Spec edge-case rule 2: non-runners stay in the list with both
            // fields null. We treat "no parseable price" as a non-runner.
            val (winPrice, winPriceRaw) = if (priceDecimal == null) (null to null) else (priceDecimal to priceRaw)
            PaddyRunner(name = name, winPrice = winPrice, winPriceRaw = winPriceRaw)
        }
    if (runners.isEmpty()) {
        System.err.println("paddy: dropping race with zero runners: $venue $startTimeRaw")
        return null
    }

    val ewRaw = root.get(Field.EW_TERMS)?.takeIf { it.isJsonPrimitive }?.asString ?: ""
    val ew = if (ewRaw.isBlank()) null else parseEachWayTerms(ewRaw)

    val marketName = "${OffsetDateTime.parse(offTime).format(HHMM)} $venue"

    return PaddyRace(
        venue = venue,
        country = country,
        offTime = offTime,
        marketName = marketName,
        raceUrl = raceUrl,
        scrapedAt = scrapedAt,
        eachWayTerms = ew,
        runners = runners,
    )
}

/**
 * Converts a UTC ISO-8601 instant (e.g. `"2026-05-09T12:30:00.000Z"`) to a
 * Europe/London ISO-8601 string with offset (`"2026-05-09T13:30:00+01:00"`
 * in BST or `"…Z"` in GMT). Returns null on parse failure.
 */
internal fun utcOrIsoToLondon(isoUtc: String): String? = try {
    val parsed = OffsetDateTime.parse(isoUtc)
    parsed.atZoneSameInstant(LONDON).toOffsetDateTime()
        .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
} catch (e: Exception) {
    null
}
```

Adjust two places to match the real fixture: (1) the `Field` constants near the top of the file, and (2) the `locateRaceArray` helper if the race array isn't at `root.races`. The behaviours (drop on missing country, drop on empty runners, preserve non-runners, EW parsing) stay the same.

- [ ] **Step 4: Fill in the synth builders in the test file**

Replace each `error(...)` body in the synth builders with a minimal JSON snippet matching your fixture's shape that exercises the one behaviour the test cares about. Keep them as small as possible — the goal is each test fails for exactly one reason.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyResponsesTest'`

Expected: 9 tests PASS.

If a test fails because the fixture's shape differs from your synth builder, your synth builder is wrong (not the parser) — fix the snippet.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: 132 tests pass (123 + 9 new).

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt
git commit -m "paddy: add parsePaddyNextRaces with edge-case handling"
```

---

## Task 5: `PaddyNextRacesFetcher` — region filter + orchestration

The fetcher wraps `PaddyClient` and `parsePaddyNextRaces`. The class-level glue is thin; the unit-tested piece is the region filter applied to a list of races.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt`:

```kotlin
package com.horsey.scraper.paddypower

import com.horsey.scraper.Regions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PaddyNextRacesFetcherTest {

    @Test
    fun `region filter keeps races whose country is in the union`() {
        val races = listOf(
            race("Lingfield", "GB"),
            race("Naas", "IE"),
            race("Belmont", "US"),
        )
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        val filtered = filterRacesByCountries(races, countries)
        assertEquals(listOf("Lingfield", "Naas"), filtered.map { it.venue })
    }

    @Test
    fun `region filter drops races whose country is outside the union`() {
        val races = listOf(race("Belmont", "US"), race("Sha Tin", "HK"))
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        assertTrue(filterRacesByCountries(races, countries).isEmpty())
    }

    @Test
    fun `region filter selecting both gb-ie and us keeps all three`() {
        val races = listOf(race("Lingfield", "GB"), race("Naas", "IE"), race("Belmont", "US"))
        val countries = Regions.countriesForAll(setOf("gb-ie", "us"))
        assertEquals(3, filterRacesByCountries(races, countries).size)
    }

    @Test
    fun `empty input gives empty output`() {
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        assertTrue(filterRacesByCountries(emptyList(), countries).isEmpty())
    }

    private fun race(venue: String, country: String) = PaddyRace(
        venue = venue, country = country,
        offTime = "2026-05-13T20:00:00+01:00",
        marketName = "20:00 $venue",
        raceUrl = "",
        scrapedAt = "2026-05-13T19:00:00Z",
        eachWayTerms = null,
        runners = listOf(PaddyRunner("Some Horse", 5.5, "9/2")),
    )
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyNextRacesFetcherTest'`

Expected: FAIL with `unresolved reference: filterRacesByCountries`.

- [ ] **Step 3: Implement `PaddyNextRacesFetcher.kt`**

Create `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`:

```kotlin
package com.horsey.scraper.paddypower

import com.horsey.scraper.Regions
import java.time.Instant

/**
 * Pure region filter. Keeps races whose `country` is in `countries`.
 * Extracted from the fetcher so it's unit-testable without HTTP.
 */
fun filterRacesByCountries(races: List<PaddyRace>, countries: Set<String>): List<PaddyRace> =
    races.filter { it.country in countries }

/**
 * Orchestrates a one-shot PaddyPower next-races scrape:
 *   1. Calls `PaddyClient.getNextRaces()` once.
 *   2. Parses the response via [parsePaddyNextRaces].
 *   3. Filters races by the union of `regions`' country codes.
 *   4. Packages the result with a run-start `scrapedAt` timestamp.
 *
 * `nowProvider` controls the timestamps for both the top-level
 * `PaddyOutput.scrapedAt` (captured at the start of `fetch`) and each
 * race's `scrapedAt` (captured just before parsing — within a
 * sub-second of the network response).
 */
class PaddyNextRacesFetcher(
    private val client: PaddyClient,
    private val nowProvider: () -> Instant = { Instant.now() },
) {
    fun fetch(regions: Set<String>): PaddyOutput {
        val runStart = nowProvider().toString()
        val json = client.getNextRaces()
        val races = parsePaddyNextRaces(json, nowProvider)
        val filtered = filterRacesByCountries(races, Regions.countriesForAll(regions))
        return PaddyOutput(
            scrapedAt = runStart,
            raceCount = filtered.size,
            races = filtered,
        )
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyNextRacesFetcherTest'`

Expected: 4 tests PASS.

(Compilation will succeed even though `PaddyClient` doesn't exist yet — the reference is unresolved only inside the class body which Kotlin compiles fine as long as the class type appears in a known package. If you get a compile error, see Task 7 — you may need to stub `PaddyClient` first. If so, create a one-line stub and then re-do Task 7 properly.)

If you do get a "unresolved reference: PaddyClient" compile error, create a minimal stub at `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`:

```kotlin
package com.horsey.scraper.paddypower
class PaddyClient { fun getNextRaces(): String = error("PaddyClient stub: replaced by real implementation in Task 7") }
```

Re-run Step 4. The 4 unit tests don't invoke `client.getNextRaces()` so the stub is sufficient.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 136 tests pass (132 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt
# Include the stub if you created one in Step 4:
git add -u src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt 2>/dev/null || true
git commit -m "paddy: add PaddyNextRacesFetcher with region filter"
```

---

## Task 6: `PaddySchemaValidator` + `PaddyValidateMain`

A standalone validator over a `paddypower.json` string, mirroring the existing `SchemaValidator` for Betfair. Includes a tiny `PaddyValidateMain` entry-point so it's runnable from `./gradlew run`.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidator.kt`
- Create: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyValidateMain.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidatorTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidatorTest.kt`:

```kotlin
package com.horsey.scraper.paddypower

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PaddySchemaValidatorTest {

    private val happy = """
        {
          "scrapedAt": "2026-05-13T20:30:00.123Z",
          "raceCount": 1,
          "races": [
            {
              "venue": "Punchestown",
              "country": "IE",
              "offTime": "2026-05-13T20:20:00+01:00",
              "marketName": "20:20 Punchestown",
              "raceUrl": "https://www.paddypower.com/horse-racing/race/x",
              "scrapedAt": "2026-05-13T20:30:00.456Z",
              "eachWayTerms": { "fraction": 0.2, "places": 3 },
              "runners": [
                { "name": "Working Class Hero", "winPrice": 5.5, "winPriceRaw": "9/2" },
                { "name": "Mister Killeens",    "winPrice": null, "winPriceRaw": null }
              ]
            }
          ]
        }
    """.trimIndent()

    @Test fun `happy path validates`() {
        assertEquals(emptyList(), validatePaddyOutput(happy))
    }

    @Test fun `raceCount mismatch is flagged`() {
        val bad = happy.replace("\"raceCount\": 1", "\"raceCount\": 5")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "raceCount" in it && "races.length" in it }, errs.toString())
    }

    @Test fun `non-ISO scrapedAt is flagged`() {
        val bad = happy.replace("2026-05-13T20:30:00.123Z", "yesterday")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "scrapedAt" in it && "ISO-8601" in it }, errs.toString())
    }

    @Test fun `non-ISO offTime is flagged`() {
        val bad = happy.replace("2026-05-13T20:20:00+01:00", "20:20")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "offTime" in it }, errs.toString())
    }

    @Test fun `EW fraction out of range is flagged`() {
        val bad = happy.replace("\"fraction\": 0.2", "\"fraction\": 1.5")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "fraction" in it }, errs.toString())
    }

    @Test fun `EW places out of range is flagged`() {
        val bad = happy.replace("\"places\": 3", "\"places\": 9")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "places" in it }, errs.toString())
    }

    @Test fun `price parity violation flagged when winPrice null but raw set`() {
        val bad = happy.replace(
            "\"winPrice\": null, \"winPriceRaw\": null",
            "\"winPrice\": null, \"winPriceRaw\": \"9/2\""
        )
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "parity" in it }, errs.toString())
    }

    @Test fun `price parity violation flagged when winPrice set but raw null`() {
        val bad = happy.replace(
            "\"winPrice\": null, \"winPriceRaw\": null",
            "\"winPrice\": 5.5, \"winPriceRaw\": null"
        )
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "parity" in it }, errs.toString())
    }

    @Test fun `missing required race field flagged`() {
        val bad = happy.replace("\"venue\": \"Punchestown\",", "")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "venue" in it }, errs.toString())
    }

    @Test fun `empty races array with zero raceCount validates`() {
        val empty = """
            { "scrapedAt": "2026-05-13T20:30:00Z", "raceCount": 0, "races": [] }
        """.trimIndent()
        assertEquals(emptyList(), validatePaddyOutput(empty))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddySchemaValidatorTest'`

Expected: FAIL with `unresolved reference: validatePaddyOutput`.

- [ ] **Step 3: Implement `PaddySchemaValidator.kt`**

Create `src/main/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidator.kt`:

```kotlin
package com.horsey.scraper.paddypower

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val EW_FRACTION_RANGE = 0.0..1.0 // exclusive zero, inclusive one — checked below
private val EW_PLACES_RANGE = 1..6

/**
 * Validates a `paddypower.json` payload string against the spec rules.
 * Returns an empty list if valid; otherwise a list of human-readable
 * error descriptions, one per violation.
 */
fun validatePaddyOutput(json: String): List<String> {
    val errors = mutableListOf<String>()
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return listOf("not valid JSON object: ${e.message}")
    }

    requireString(root, "scrapedAt", errors) { v ->
        if (!isIsoUtc(v)) errors += "top-level scrapedAt is not ISO-8601 UTC instant: '$v'"
    }
    val raceCount = requireInt(root, "raceCount", errors)
    val racesEl = root.get("races")
    if (racesEl == null || !racesEl.isJsonArray) {
        errors += "races: missing or not array"
        return errors
    }
    val races = racesEl.asJsonArray
    if (raceCount != null && raceCount != races.size()) {
        errors += "raceCount ($raceCount) != races.length (${races.size()})"
    }

    races.forEachIndexed { i, raceEl ->
        val ctx = "races[$i]"
        if (!raceEl.isJsonObject) { errors += "$ctx: not an object"; return@forEachIndexed }
        val race = raceEl.asJsonObject

        requireString(race, "venue", errors)
        requireString(race, "country", errors)
        requireString(race, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(race, "marketName", errors)
        requireString(race, "raceUrl", errors)
        requireString(race, "scrapedAt", errors) { v ->
            if (!isIsoUtc(v)) errors += "$ctx.scrapedAt not ISO-8601 UTC: '$v'"
        }

        val ewEl = race.get("eachWayTerms")
        if (ewEl != null && !ewEl.isJsonNull) {
            if (!ewEl.isJsonObject) {
                errors += "$ctx.eachWayTerms: not an object or null"
            } else {
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
        }

        val runnersEl = race.get("runners")
        if (runnersEl == null || !runnersEl.isJsonArray) {
            errors += "$ctx.runners: missing or not array"
            return@forEachIndexed
        }
        runnersEl.asJsonArray.forEachIndexed { j, rEl ->
            val rctx = "$ctx.runners[$j]"
            if (!rEl.isJsonObject) { errors += "$rctx: not an object"; return@forEachIndexed }
            val r = rEl.asJsonObject
            requireString(r, "name", errors)
            val wp = r.get("winPrice")
            val raw = r.get("winPriceRaw")
            val wpNull = wp == null || wp.isJsonNull
            val rawNull = raw == null || raw.isJsonNull
            if (wpNull != rawNull) {
                errors += "$rctx: price parity violation — winPrice null=$wpNull, winPriceRaw null=$rawNull"
            }
            if (!wpNull && (!wp!!.isJsonPrimitive || !wp.asJsonPrimitive.isNumber)) {
                errors += "$rctx.winPrice: not a number"
            }
            if (!rawNull && (!raw!!.isJsonPrimitive || !raw.asJsonPrimitive.isString)) {
                errors += "$rctx.winPriceRaw: not a string"
            }
        }
    }
    return errors
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

- [ ] **Step 4: Implement `PaddyValidateMain.kt`**

Create `src/main/kotlin/com/horsey/scraper/paddypower/PaddyValidateMain.kt`:

```kotlin
package com.horsey.scraper.paddypower

import java.io.File

/**
 * Entry point for ad-hoc validation:
 *   ./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json
 */
fun main(args: Array<String>) {
    require(args.size == 1) { "usage: PaddyValidateMain <path-to-paddypower.json>" }
    val path = args[0]
    val errors = validatePaddyOutput(File(path).readText())
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

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddySchemaValidatorTest'`

Expected: 10 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: 146 tests pass (136 + 10 new).

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidator.kt src/main/kotlin/com/horsey/scraper/paddypower/PaddyValidateMain.kt src/test/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidatorTest.kt
git commit -m "paddy: add PaddySchemaValidator and PaddyValidateMain"
```

---

## Task 7: `PaddyClient` — HTTP transport

The thin HTTP wrapper. Uses the URL captured in Task 0's
`src/test/resources/paddy-next-races-endpoint.txt`. No unit tests
(would require mocking `HttpClient`); the pure builders/parsers it
glues together are tested elsewhere.

**Files:**
- Create or replace (if Task 5 stubbed it): `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`

- [ ] **Step 1: Read the endpoint metadata**

Run: `cat src/test/resources/paddy-next-races-endpoint.txt`

Note the URL, method, and any required headers.

- [ ] **Step 2: Replace `PaddyClient.kt`**

```kotlin
package com.horsey.scraper.paddypower

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

// Paste the URL from src/test/resources/paddy-next-races-endpoint.txt:
private const val NEXT_RACES_URL = "<PASTE URL HERE>"

// Realistic recent Chrome UA. Bookmakers commonly block obviously-bot UAs.
private const val USER_AGENT =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

/**
 * Thin HTTP transport for PaddyPower's next-races JSON endpoint.
 *
 * No auth, no retries, no rate-limit handling. One request per call.
 * Non-2xx responses throw `IllegalStateException` with the status code
 * and the first 500 chars of the body — same shape as `BetfairClient`.
 */
class PaddyClient(
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build(),
) {
    fun getNextRaces(): String {
        val req = HttpRequest.newBuilder()
            .uri(URI.create(NEXT_RACES_URL))
            .timeout(Duration.ofSeconds(20))
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/json")
            // If endpoint.txt lists method=POST, change the next line to:
            //   .POST(HttpRequest.BodyPublishers.noBody())
            .GET()
            .build()
        val res: HttpResponse<String> = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (res.statusCode() / 100 != 2) {
            val snip = res.body().take(500)
            error("HTTP ${res.statusCode()} from ${req.uri()}: $snip")
        }
        return res.body()
    }
}
```

Adjust the `.GET()` call and any custom headers per the metadata file. If a header like `X-NEDS-TOKEN` was captured, add it. If the endpoint requires a query parameter (e.g. `?country=GB`), append it to `NEXT_RACES_URL`.

- [ ] **Step 3: Compile**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`. The URL constant doesn't have to be valid for compile — the runtime call would fail, but tests don't make live HTTP calls.

- [ ] **Step 4: Run the full suite**

Run: `./gradlew test`

Expected: 146 tests pass (no new tests in this task).

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt
git commit -m "paddy: add PaddyClient HTTP transport"
```

---

## Task 8: Wire into `Main.kt`

After the Betfair pipeline succeeds, run the PaddyPower pipeline and write `paddypower.json`. A PaddyPower failure must not lose the Betfair output (which is already on disk by the time PP runs).

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Inspect current `Main.kt`**

Run: `cat src/main/kotlin/com/horsey/scraper/Main.kt | tail -30`

The file ends with:

```kotlin
    File(OUTPUT_FILE).writeText(gson.toJson(output))
    println("\nWrote $OUTPUT_FILE (${results.size} races)")
}
```

You'll add a new block after `println("\nWrote $OUTPUT_FILE …")` and before the closing `}`.

- [ ] **Step 2: Add the PaddyPower block**

Append this code immediately before the closing `}` of `fun main`:

```kotlin

    // ---------- PaddyPower phase ----------
    //
    // Runs only after the Betfair pipeline has fully completed and
    // written data.json. A PaddyPower failure exits non-zero so the
    // user sees the failure, but the Betfair output is preserved.
    println("\nFetching PaddyPower next-races…")
    val ppOutput = try {
        com.horsey.scraper.paddypower.PaddyNextRacesFetcher(
            com.horsey.scraper.paddypower.PaddyClient()
        ).fetch(regions)
    } catch (e: Exception) {
        System.err.println("Error fetching PaddyPower: ${e.message}")
        kotlin.system.exitProcess(1)
    }
    File("paddypower.json").writeText(gson.toJson(ppOutput))
    println("Wrote paddypower.json (${ppOutput.raceCount} races)")
```

- [ ] **Step 3: Compile**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 4: Run the full suite**

Run: `./gradlew test`

Expected: 146 tests pass (no new tests).

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "Main.kt: run PaddyPower scrape after Betfair, write paddypower.json"
```

---

## Task 9: Final validation

Verification only — no code changes, no commits.

- [ ] **Step 1: Full test run**

Run: `./gradlew test 2>&1 | tail -10`

Expected: `BUILD SUCCESSFUL`. Test total should be approximately 146.

- [ ] **Step 2: Compile + assemble**

Run: `./gradlew compileKotlin compileTestKotlin assemble`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Validator entry-point is reachable**

Run: `./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=nonexistent.json 2>&1 | head -5`

Expected: an error message (file not found is fine). The point is the main class loads.

- [ ] **Step 4: List the commits added by this plan**

Run: `git log --oneline 1664178..HEAD`

(The base SHA `1664178` is the spec commit. Adjust if your branch base differs.)

Expected: roughly nine commits, one per task.

- [ ] **Step 5: Surface the live smoke step to the user**

Don't run a live scrape unattended — it requires the user's existing Betfair credentials at `~/.horsey-scraper/credentials.json` and an active internet connection.

Tell the user:

> "PaddyPower scraper merged. To smoke-test live: run `./run.sh`. Expected: produces both `data.json` and `paddypower.json` (the latter has races filtered to GB+IE). Validate `paddypower.json` with `./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json` — expected output: `paddypower.json: VALID (matches spec)`."

No commit in this task.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Arb-finder.** Joining `data.json` and `paddypower.json` to surface arbitrage opportunities is its own project.
- **Venue-name normalisation.** PaddyPower may show "Lingfield Park" while Betfair shows "Lingfield". A normalisation table belongs in the arb-finder, not here.
- **Retries / rate-limit handling.** PP's next-races view is light traffic; if you start running this every few minutes, polite backoff is worth adding.
- **Full-day scrape.** v1 captures only what's on the next-races view (≤10 races). Scraping every race today across multiple meeting pages is a future extension.
- **Race-type snippet in `marketName`.** v1 uses `"HH:mm Venue"`. If PP exposes a clean race-type descriptor (e.g. "5f Hcap"), `marketName` becomes `"HH:mm Venue - <type>"` to match Betfair. Deferred to keep v1 simple.
- **Additional bookmakers.** Bet365, William Hill, etc. each get their own sub-package and JSON output file, following this PaddyPower pattern.
- **Playwright fallback path.** If PP changes their architecture and the JSON endpoint goes away, the documented fallback is `com.microsoft.playwright:playwright`. That's a separate plan.
