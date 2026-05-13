# PaddyPower Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-shot PaddyPower next-races scraper that writes a `paddypower.json` snapshot (horse names, decimal+fractional win prices, per-race each-way terms) alongside the existing Betfair `betfair.json`. First of N bookmaker scrapers.

**Architecture:** New sub-package `com.horsey.scraper.paddypower`. Hand-rolled HTTP via `java.net.http.HttpClient` against PaddyPower's internal JSON endpoint (discovered in Task 0). Pure parsers convert the response into domain types, region filter drops out-of-scope races, schema validator enforces the output contract. Runs from `Main.kt` after the Betfair pipeline.

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`, Gson, `java.net.http.HttpClient` from the JDK. No new Maven dependencies.

**Spec:** `docs/superpowers/specs/2026-05-13-paddypower-scraper-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- This is a Kotlin/JVM one-shot CLI that already produces `betfair.json` from the Betfair Exchange API. You're adding a second output, `paddypower.json`, from PaddyPower's public next-races view.
- Output shape is fixed by the spec — read the spec before starting. `paddypower.json` is independent of `betfair.json`; the two files are joined later by a separate (out-of-scope) arb-finder.
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
 *
 * `selectionId` is the same selection id Betfair uses for this horse,
 * letting an arb-finder join PaddyPower runners directly to Betfair
 * `betfair.json` runners without horse-name normalisation. Nullable so
 * future bookmakers without this affordance can still produce records.
 */
data class PaddyRunner(
    val name: String,
    val selectionId: Long?,
    val winPrice: Double?,
    val winPriceRaw: String?,
)

/**
 * One race as observed on PaddyPower's next-races view. `offTime` is an
 * ISO-8601 string with Europe/London offset, formatted identically to
 * the Betfair side's `offTime` so a string compare suffices as a join
 * key. `country` is ISO 3166-1 alpha-2.
 *
 * `betfairWinMarketId` is the matching Betfair Exchange WIN market id
 * (e.g. `"1.258114325"`), which PaddyPower exposes on its API. Acts as
 * the direct join key against `betfair.json[].raceId`. Nullable so future
 * bookmakers without this affordance can still produce records.
 */
data class PaddyRace(
    val venue: String,
    val country: String,
    val offTime: String,
    val marketName: String,
    val raceUrl: String,
    val scrapedAt: String,
    val betfairWinMarketId: String?,
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

## Task 3: ~~`parseEachWayTerms`~~ — SUPERSEDED

**Skip this task.** The fixture captured in Task 0 shows that PaddyPower's
API returns each-way terms as structured fields (`numberOfPlaces: 4`,
`placeFraction: { numerator: 1, denominator: 5 }`), not as a text string.
Parsing text is therefore dead code on the PP scrape path. The
`EachWayTerms` data class is still defined in Task 1; the next task
constructs values of it directly from the structured JSON fields.

If a future bookmaker returns EW terms as text and needs a parser,
re-introduce this task then.

---

## Task 4: `parsePaddyNextRaces` — JSON → `List<PaddyRace>`

Now grounded in the real fixture from Task 0. The PaddyPower
`content-managed-page/v7` response has this shape (abridged):

```text
{
  "layout":      { "cards": { "19424": { "raceIds": [...] } } },
  "attachments": {
    "races":   { "<raceId>": { raceId, winMarketId, winMarketName,
                              startTime, countryCode, venue, meetingId } },
    "markets": { "<marketId>": { marketId, raceId, marketName, marketType,
                                  exchangeMarketId, runners[...],
                                  numberOfPlaces, placeFraction:{numerator,denominator},
                                  eachwayAvailable } },
    "meetings":{ ... }
  }
}
```

Races and markets are joined by `race.winMarketId == market.marketId`.
Each market's `exchangeMarketId` (e.g. `"1.258114325"`) is the matching
Betfair WIN market id — captured as `betfairWinMarketId`. Each runner
carries `selectionId`, `runnerName`, `runnerStatus`, and prices in
`winRunnerOdds.trueOdds.{decimalOdds.decimalOdds, fractionalOdds.{numerator,denominator}}`.

Three runner names are synthetic placeholders we must filter out:
`"Unnamed Favourite"`, `"Unnamed 2nd Favourite"`, `"The Field"`.

EW terms are structured (not text): build `EachWayTerms` directly from
`numberOfPlaces` and `placeFraction` when `eachwayAvailable == true`.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- Create: `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt`

- [ ] **Step 1: Verify the fixture is present**

Run: `test -f src/test/resources/paddy-next-races-sample.json && wc -c src/test/resources/paddy-next-races-sample.json`

Expected: the file exists with several thousand bytes. If missing, Task 0 wasn't completed — return BLOCKED.

Create `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt`:

```kotlin
package com.horsey.scraper.paddypower

import java.nio.file.Files
import java.nio.file.Paths
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Tests for `parsePaddyNextRaces`.
 *
 * The PaddyPower next-races JSON shape (captured 2026-05-13 from
 * `apisms.paddypower.com/smspp/content-managed-page/v7`) is:
 *   {
 *     "layout":      { ... cards listing raceIds ... },
 *     "attachments": {
 *       "races":   { "<raceId>": { raceId, winMarketId, winMarketName,
 *                                  startTime, countryCode, venue, ... } },
 *       "markets": { "<marketId>": { marketId, raceId, marketType,
 *                                    exchangeMarketId, runners[...],
 *                                    numberOfPlaces,
 *                                    placeFraction:{numerator,denominator},
 *                                    eachwayAvailable } }
 *     }
 *   }
 *
 * Races and markets are joined by `race.winMarketId == market.marketId`.
 * Each runner carries `selectionId`, `runnerName`, `runnerStatus`,
 * and prices in `winRunnerOdds.trueOdds.{decimalOdds.decimalOdds,
 * fractionalOdds:{numerator,denominator}}`.
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
        assertTrue(first.venue.isNotBlank())
        assertTrue(first.country.isNotBlank())
        assertTrue(
            first.offTime.matches(Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)""")),
            "offTime must be ISO-8601 with offset, got '${first.offTime}'",
        )
        assertEquals(fixedNow.toString(), first.scrapedAt)
        assertTrue(first.runners.isNotEmpty(), "race must have at least one runner")
    }

    @Test
    fun `synthetic runners are filtered out`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val allNames = races.flatMap { it.runners.map { r -> r.name } }
        assertTrue(allNames.isNotEmpty())
        for (synthetic in listOf("Unnamed Favourite", "Unnamed 2nd Favourite", "The Field")) {
            assertTrue(synthetic !in allNames, "found synthetic runner '$synthetic' in output")
        }
    }

    @Test
    fun `marketName is HH_mm Venue - race-type`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        // Salisbury market is 16:40 UTC = 17:40 BST in May → "17:40 Salisbury - 6f Hcap"
        assertEquals("17:40 Salisbury - 6f Hcap", race.marketName)
    }

    @Test
    fun `betfairWinMarketId is captured from market exchangeMarketId`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        assertEquals("1.258114325", race.betfairWinMarketId)
    }

    @Test
    fun `selectionId is captured on each runner`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        val stoleMyHeart = race.runners.first { it.name == "Stole My Heart" }
        assertEquals(28252276L, stoleMyHeart.selectionId)
    }

    @Test
    fun `decimal and fractional prices are both populated`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        val r = race.runners.first { it.name == "Stole My Heart" }
        // fixture has decimalOdds=21, fractionalOdds 20/1
        assertEquals(21.0, r.winPrice)
        assertEquals("20/1", r.winPriceRaw)
    }

    @Test
    fun `each-way terms come from numberOfPlaces and placeFraction`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        // fixture: numberOfPlaces=4, placeFraction 1/5
        assertEquals(EachWayTerms(0.2, 4), race.eachWayTerms)
    }

    @Test
    fun `race without country code is dropped`() {
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "venue": "Nowhere" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN", "runners": [],
                                     "exchangeMarketId": "1.x" } } } }
        """.trimIndent()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `race with zero real runners is dropped`() {
        // All runners are synthetic placeholders → effectively empty.
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN",
                                     "exchangeMarketId": "1.x",
                                     "numberOfPlaces": 3,
                                     "placeFraction": {"numerator":1,"denominator":5},
                                     "eachwayAvailable": true,
                                     "runners": [
                                       { "selectionId": 10518227, "runnerName": "Unnamed Favourite", "runnerStatus": "ACTIVE" },
                                       { "selectionId": 327679,   "runnerName": "The Field",         "runnerStatus": "REMOVED" }
                                     ] } } } }
        """.trimIndent()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `runner with REMOVED status keeps both price fields null`() {
        // Construct a race with one normal runner + one withdrawn real horse.
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN",
                                     "exchangeMarketId": "1.x",
                                     "numberOfPlaces": 3,
                                     "placeFraction": {"numerator":1,"denominator":5},
                                     "eachwayAvailable": true,
                                     "runners": [
                                       { "selectionId": 1001, "runnerName": "Real Horse", "runnerStatus": "ACTIVE",
                                         "winRunnerOdds": { "trueOdds": { "decimalOdds": {"decimalOdds":5.0},
                                                                          "fractionalOdds": {"numerator":4,"denominator":1} } } },
                                       { "selectionId": 1002, "runnerName": "Withdrawn Horse", "runnerStatus": "REMOVED" }
                                     ] } } } }
        """.trimIndent()
        val race = parsePaddyNextRaces(json, nowProvider).single()
        val withdrawn = race.runners.first { it.name == "Withdrawn Horse" }
        assertNull(withdrawn.winPrice)
        assertNull(withdrawn.winPriceRaw)
        assertNotNull(race.runners.firstOrNull { it.name == "Real Horse" })
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyResponsesTest'`

Expected: FAIL with `unresolved reference: parsePaddyNextRaces`.

- [ ] **Step 4: Implement `parsePaddyNextRaces`**

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

// PaddyPower's synthetic placeholders that appear in every market and are
// not actual horses. Filter by name (selection ids 10518227, 10518230,
// 327679 would work too; name-based is more portable across endpoints).
private val SYNTHETIC_RUNNER_NAMES =
    setOf("Unnamed Favourite", "Unnamed 2nd Favourite", "The Field")

/**
 * Shreds a PaddyPower next-races JSON response into [PaddyRace] objects.
 *
 * Expected shape (see test class KDoc for full details):
 *   `attachments.races[id]`   → race metadata, joins to `markets[winMarketId]`
 *   `attachments.markets[id]` → runners, EW terms, exchangeMarketId
 *
 * Drops races that:
 *   - have no country code (region filter would be unsafe)
 *   - have no joined WIN market
 *   - have zero non-synthetic, non-empty runners after filtering
 *
 * Non-runners (`runnerStatus = "REMOVED"`) are preserved in the runner list
 * with both price fields null. Each race carries the [nowProvider]'s
 * timestamp as `scrapedAt`.
 */
fun parsePaddyNextRaces(
    json: String,
    nowProvider: () -> Instant = { Instant.now() },
): List<PaddyRace> {
    val root = JsonParser.parseString(json).asJsonObject
    val attachments = root.get("attachments")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()
    val racesObj = attachments.get("races")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()
    val marketsObj = attachments.get("markets")?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return emptyList()

    val scrapedAt = nowProvider().toString()
    val out = mutableListOf<PaddyRace>()
    for ((_, raceEl) in racesObj.entrySet()) {
        if (!raceEl.isJsonObject) continue
        val race = paddyRaceFromJson(raceEl.asJsonObject, marketsObj, scrapedAt) ?: continue
        out += race
    }
    return out
}

private fun paddyRaceFromJson(
    raceJson: JsonObject,
    marketsObj: JsonObject,
    scrapedAt: String,
): PaddyRace? {
    val venue = raceJson.string("venue") ?: return null
    val country = raceJson.string("countryCode")?.takeIf { it.isNotBlank() } ?: run {
        System.err.println("paddy: dropping race with no country at venue=$venue")
        return null
    }
    val startTimeUtc = raceJson.string("startTime") ?: return null
    val offTime = utcToLondon(startTimeUtc) ?: return null
    val winMarketId = raceJson.string("winMarketId") ?: return null
    val raceType = raceJson.string("winMarketName") ?: ""

    val marketJson = marketsObj.get(winMarketId)?.takeIf { it.isJsonObject }?.asJsonObject
        ?: return null

    val runners = parsePaddyRunners(marketJson)
    if (runners.isEmpty()) {
        System.err.println("paddy: dropping race with zero runners: $venue $startTimeUtc")
        return null
    }

    val ew = parseStructuredEachWay(marketJson)
    val betfairId = marketJson.string("exchangeMarketId")

    val time = OffsetDateTime.parse(offTime).format(HHMM)
    val marketName = if (raceType.isBlank()) "$time $venue" else "$time $venue - $raceType"

    return PaddyRace(
        venue = venue,
        country = country,
        offTime = offTime,
        marketName = marketName,
        raceUrl = "",  // PaddyPower doesn't expose a per-race deep link in this endpoint
        scrapedAt = scrapedAt,
        betfairWinMarketId = betfairId,
        eachWayTerms = ew,
        runners = runners,
    )
}

private fun parsePaddyRunners(marketJson: JsonObject): List<PaddyRunner> {
    val runners = marketJson.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray
        ?: return emptyList()
    val out = mutableListOf<PaddyRunner>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val name = r.string("runnerName") ?: continue
        if (name in SYNTHETIC_RUNNER_NAMES) continue
        val selectionId = r.long("selectionId")
        val status = r.string("runnerStatus") ?: "ACTIVE"
        val odds = r.get("winRunnerOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.get("trueOdds")?.takeIf { it.isJsonObject }?.asJsonObject
        val isActiveWithOdds = status == "ACTIVE" && odds != null
        val winPrice: Double? = odds
            ?.get("decimalOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.double("decimalOdds")
            ?.takeIf { isActiveWithOdds }
        val winPriceRaw: String? = odds
            ?.get("fractionalOdds")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.let { fOdds ->
                val n = fOdds.int("numerator") ?: return@let null
                val d = fOdds.int("denominator") ?: return@let null
                "$n/$d"
            }
            ?.takeIf { isActiveWithOdds }
        out += PaddyRunner(
            name = name,
            selectionId = selectionId,
            winPrice = winPrice,
            winPriceRaw = winPriceRaw,
        )
    }
    return out
}

private fun parseStructuredEachWay(marketJson: JsonObject): EachWayTerms? {
    val available = marketJson.get("eachwayAvailable")?.takeIf { it.isJsonPrimitive }
        ?.asJsonPrimitive?.takeIf { it.isBoolean }?.asBoolean ?: true
    if (!available) return null
    val places = marketJson.int("numberOfPlaces") ?: return null
    if (places <= 0) return null
    val frac = marketJson.get("placeFraction")?.takeIf { it.isJsonObject }?.asJsonObject ?: return null
    val num = frac.int("numerator") ?: return null
    val den = frac.int("denominator") ?: return null
    if (den == 0) return null
    val fraction = num.toDouble() / den.toDouble()
    if (fraction <= 0.0 || fraction > 1.0) return null
    return EachWayTerms(fraction, places)
}

/**
 * Converts a UTC ISO-8601 instant (e.g. `"2026-05-14T16:40:00.000Z"`) to a
 * Europe/London ISO-8601 string with offset (`"2026-05-14T17:40:00+01:00"`
 * in BST or `"…Z"` in GMT). Returns null on parse failure.
 */
internal fun utcToLondon(isoUtc: String): String? = try {
    OffsetDateTime.parse(isoUtc)
        .atZoneSameInstant(LONDON).toOffsetDateTime()
        .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
} catch (e: Exception) {
    null
}

// Tiny JSON helpers — keep guards uniform across this file.
private fun JsonObject.string(key: String): String? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
private fun JsonObject.int(key: String): Int? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asInt
private fun JsonObject.long(key: String): Long? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asLong
private fun JsonObject.double(key: String): Double? =
    get(key)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asDouble
```

Move the new `import` lines to the existing import block at the top of `PaddyResponses.kt`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyResponsesTest'`

Expected: 10 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: 122 tests pass (95 baseline + 17 from Task 2 + 10 new in this task).

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt
git commit -m "paddy: add parsePaddyNextRaces with fixture-grounded parser"
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

Expected: 126 tests pass (122 + 4 new).

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
              "marketName": "20:20 Punchestown - 2m INHF",
              "raceUrl": "",
              "scrapedAt": "2026-05-13T20:30:00.456Z",
              "betfairWinMarketId": "1.258114325",
              "eachWayTerms": { "fraction": 0.2, "places": 3 },
              "runners": [
                { "name": "Working Class Hero", "selectionId": 71384199, "winPrice": 5.5, "winPriceRaw": "9/2" },
                { "name": "Mister Killeens",    "selectionId": 55504985, "winPrice": null, "winPriceRaw": null }
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

Expected: 136 tests pass (126 + 10 new).

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidator.kt src/main/kotlin/com/horsey/scraper/paddypower/PaddyValidateMain.kt src/test/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidatorTest.kt
git commit -m "paddy: add PaddySchemaValidator and PaddyValidateMain"
```

---

## Task 7: `PaddyClient` — Playwright transport

Hand-rolled HTTP is not viable: every PaddyPower API subdomain is
behind Cloudflare Bot Fight Mode, which blocks raw HTTP clients
regardless of headers. The transport drives headless Chromium via
Playwright, which executes the Cloudflare challenge JS naturally and
fetches the JSON like a real browser.

**Files:**
- Modify: `build.gradle.kts` — add Playwright + its lifecycle plugin (the
  bundled-browser download triggers via a Gradle task).
- Create or replace: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`

- [ ] **Step 1: Add Playwright to `build.gradle.kts`**

Append to the `dependencies { … }` block (alongside the existing
`com.google.code.gson:gson` entry):

```kotlin
    implementation("com.microsoft.playwright:playwright:1.47.0")
```

- [ ] **Step 2: Install the browser binary**

Run: `./gradlew --no-daemon --quiet build -x test 2>&1 | tail -5`
(this fetches the Playwright jar). Then run:

```bash
./gradlew --no-daemon -q "javaExec" 2>/dev/null || true
# Bootstrap the Chromium bundle Playwright uses:
mkdir -p ~/.cache/ms-playwright
java -cp "$(./gradlew -q --no-daemon dependencies --configuration runtimeClasspath 2>/dev/null | grep -o '/Users/.*playwright-1.47.0.jar' | head -1)" com.microsoft.playwright.CLI install chromium
```

If that one-liner is awkward, do the equivalent via Playwright's
documented bootstrap: `./gradlew run -PmainClass=com.microsoft.playwright.CLI --args="install chromium"`.
Either path leaves the Chromium binary in `~/.cache/ms-playwright/`.

Expected: a `chromium-<version>` directory exists under
`~/.cache/ms-playwright/`. The next steps depend on this.

- [ ] **Step 3: Implement `PaddyClient.kt`**

Create `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`:

```kotlin
package com.horsey.scraper.paddypower

import com.microsoft.playwright.Browser
import com.microsoft.playwright.BrowserType
import com.microsoft.playwright.Playwright
import com.microsoft.playwright.options.LoadState

// URL captured 2026-05-13 — see src/test/resources/paddy-next-races-endpoint.txt.
private const val NEXT_RACES_URL =
    "https://apisms.paddypower.com/smspp/content-managed-page/v7" +
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl" +
    "&cardsToFetch=19424&countryCode=IE&currencyCode=EUR&eventTypeId=7" +
    "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false" +
    "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true" +
    "&language=en&layoutFetchedCardsOnly=true&loggedIn=false" +
    "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE" +
    "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY" +
    "&timezone=Europe%2FDublin"

// Visit the parent page first so Cloudflare drops the cf_clearance cookie
// in the browser session before we hit the API.
private const val WARMUP_URL = "https://www.paddypower.com/horse-racing"

/**
 * Fetches PaddyPower's next-races JSON via a real headless Chromium
 * instance so Cloudflare's bot challenge resolves naturally.
 *
 * Flow:
 *   1. Launch headless Chromium.
 *   2. Visit the public horse-racing landing page; wait for it to settle.
 *      This earns the `cf_clearance` cookie scoped to *.paddypower.com.
 *   3. Fetch the JSON endpoint via the in-page `fetch()` API so the
 *      browser's TLS / cookie / fingerprint state carries through.
 *   4. Return the response body as a String.
 *
 * Each call launches and tears down its own browser. For a one-shot CLI
 * that's acceptable (~2-3 s of fixed overhead). If we ever need multiple
 * scrapes per run, hoist the browser into a lifecycle-managed singleton.
 */
class PaddyClient {
    fun getNextRaces(): String {
        Playwright.create().use { pw ->
            val browser: Browser = pw.chromium().launch(
                BrowserType.LaunchOptions().setHeadless(true),
            )
            try {
                val context = browser.newContext(
                    Browser.NewContextOptions()
                        .setUserAgent(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
                            "AppleWebKit/537.36 (KHTML, like Gecko) " +
                            "Chrome/126.0.0.0 Safari/537.36",
                        )
                        .setLocale("en-GB")
                        .setTimezoneId("Europe/Dublin"),
                )
                val page = context.newPage()
                page.navigate(WARMUP_URL)
                page.waitForLoadState(LoadState.NETWORKIDLE)

                // Fetch from inside the page so Cloudflare cookies + TLS fingerprint
                // are used. evaluate() returns the response body.
                val body = page.evaluate(
                    """
                    async (url) => {
                        const r = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: { 'accept': 'application/json, text/plain, */*' },
                        });
                        if (!r.ok) {
                            const text = await r.text();
                            throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 500));
                        }
                        return await r.text();
                    }
                    """.trimIndent(),
                    NEXT_RACES_URL,
                ) as? String

                return body ?: error("PaddyClient: empty response body from $NEXT_RACES_URL")
            } finally {
                browser.close()
            }
        }
    }
}
```

- [ ] **Step 4: Compile**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`. Playwright classes resolve via the new dependency.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: no new tests added; total unchanged (122 from after Task 4).

- [ ] **Step 6: Commit**

```bash
git add build.gradle.kts src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt
git commit -m "paddy: add PaddyClient (Playwright transport for Cloudflare-gated endpoint)"
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
    // written betfair.json. A PaddyPower failure exits non-zero so the
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

Expected: 136 tests pass (no new tests).

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

Expected: `BUILD SUCCESSFUL`. Test total should be approximately 136.

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

> "PaddyPower scraper merged. To smoke-test live: run `./run.sh`. Expected: produces both `betfair.json` and `paddypower.json` (the latter has races filtered to GB+IE). Validate `paddypower.json` with `./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json` — expected output: `paddypower.json: VALID (matches spec)`."

No commit in this task.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Arb-finder.** Joining `betfair.json` and `paddypower.json` to surface arbitrage opportunities is its own project.
- **Venue-name normalisation.** PaddyPower may show "Lingfield Park" while Betfair shows "Lingfield". A normalisation table belongs in the arb-finder, not here.
- **Retries / rate-limit handling.** PP's next-races view is light traffic; if you start running this every few minutes, polite backoff is worth adding.
- **Full-day scrape.** v1 captures only what's on the next-races view (≤10 races). Scraping every race today across multiple meeting pages is a future extension.
- **Race-type snippet in `marketName`.** v1 uses `"HH:mm Venue"`. If PP exposes a clean race-type descriptor (e.g. "5f Hcap"), `marketName` becomes `"HH:mm Venue - <type>"` to match Betfair. Deferred to keep v1 simple.
- **Additional bookmakers.** Bet365, William Hill, etc. each get their own sub-package and JSON output file, following this PaddyPower pattern.
- **Playwright fallback path.** If PP changes their architecture and the JSON endpoint goes away, the documented fallback is `com.microsoft.playwright:playwright`. That's a separate plan.
