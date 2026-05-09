# Multi-market lay-price output schema — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape `data.json` to a per-horse pivot of best-lay prices across `WIN` + `TOP_2` / `TOP_3` / `TOP_4` / `TOP_5` Finish markets, with key-presence semantics that distinguish "no lay on offer" from "market not scraped."

**Architecture:** One Chrome session per race. Navigate to Win, extract runners (the source-of-truth list), discover Top-N URLs from the related-markets DOM, navigate to each, extract lay-by-name, then pivot all five into one per-runner `lay` map. Pure logic (parsers, pivot, validator) lives outside the browser code so it can be unit-tested.

**Tech Stack:** Kotlin 1.9, Selenium 4.16 (Chrome), Gson 2.10, JUnit 5 via `kotlin("test")`. JDK 17.

**Spec:** `docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- `./gradlew run --quiet` (or `./run.sh`) runs `Main.kt`, which scrapes today's Betfair Exchange UK + IE races and writes `data.json`.
- `./gradlew run -PmainClass=com.horsey.scraper.SomethingMainKt` runs an alternate entry point — the `Test*Main.kt` and `Debug*Main.kt` files use this pattern.
- All scraping is Selenium driving a real Chrome (`WebDriverUtils.kt:createChromeDriver`). Pages are heavy SPA Angular; we wait for DOM elements, then use `JavascriptExecutor` to walk the DOM and pull text out as `|||`-delimited strings.
- There are no tests yet. Task 1 sets up the framework.
- Betfair race URLs look like `https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314`. The `1.249508314` is a stable per-market ID. The `1.` prefix is consistent across all markets we touch.
- The race list shows times as local-UK `HH:mm` (e.g. `13:30`). Today's date in `Europe/London` + that string = the off-time.

When in doubt, **read the spec** — the "Edge-case rules" table is normative and the validator (Task 14) encodes it.

---

## Task 1: Add test framework

**Files:**
- Modify: `build.gradle.kts`
- Create: `src/test/kotlin/com/horsey/scraper/SanityTest.kt`

- [ ] **Step 1: Add the test dependency**

Modify `build.gradle.kts`. Replace the `dependencies { ... }` block with:

```kotlin
dependencies {
    implementation("org.seleniumhq.selenium:selenium-java:4.16.1")
    implementation("org.slf4j:slf4j-simple:2.0.9")
    implementation("com.google.code.gson:gson:2.10.1")

    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
}
```

- [ ] **Step 2: Write a sanity test**

Create `src/test/kotlin/com/horsey/scraper/SanityTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals

class SanityTest {
    @Test
    fun `test framework wired up`() {
        assertEquals(4, 2 + 2)
    }
}
```

- [ ] **Step 3: Run it**

Run: `./gradlew test`
Expected: `BUILD SUCCESSFUL`, `SanityTest > test framework wired up() PASSED` in the report.

- [ ] **Step 4: Commit**

```bash
git add build.gradle.kts src/test/kotlin/com/horsey/scraper/SanityTest.kt
git commit -m "Add JUnit 5 test framework via kotlin(\"test\")"
```

---

## Task 2: MarketType enum

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Models.kt`
- Create: `src/test/kotlin/com/horsey/scraper/MarketTypeTest.kt`

- [ ] **Step 1: Write the failing test**

Create `src/test/kotlin/com/horsey/scraper/MarketTypeTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals

class MarketTypeTest {
    @Test
    fun `has the five expected values in declared order`() {
        assertEquals(
            listOf("WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"),
            MarketType.values().map { it.name }
        )
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew test --tests 'com.horsey.scraper.MarketTypeTest'`
Expected: FAIL with `unresolved reference: MarketType`.

- [ ] **Step 3: Add the enum**

Open `src/main/kotlin/com/horsey/scraper/Models.kt`. At the top of the file (after the `package` line), add:

```kotlin
enum class MarketType { WIN, TOP_2, TOP_3, TOP_4, TOP_5 }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./gradlew test --tests 'com.horsey.scraper.MarketTypeTest'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Models.kt src/test/kotlin/com/horsey/scraper/MarketTypeTest.kt
git commit -m "Add MarketType enum (WIN, TOP_2..TOP_5)"
```

---

## Task 3: Race ID parser

Pure function: extract the `1.NNN` ID from a Betfair market URL.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RaceIdParser.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RaceIdParserTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RaceIdParserTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RaceIdParserTest {
    @Test
    fun `extracts ID from canonical market URL`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `extracts ID with trailing slash`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314/"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `extracts ID with query string`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314?source=foo"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `returns null when no 1-dot-digits segment present`() {
        assertNull(extractRaceId("https://www.betfair.com/exchange/plus/en/horse-racing"))
    }

    @Test
    fun `returns null on empty input`() {
        assertNull(extractRaceId(""))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceIdParserTest'`
Expected: FAIL with `unresolved reference: extractRaceId`.

- [ ] **Step 3: Implement**

Create `src/main/kotlin/com/horsey/scraper/RaceIdParser.kt`:

```kotlin
package com.horsey.scraper

private val RACE_ID = Regex("""\b(1\.\d+)\b""")

/**
 * Extracts a Betfair race/market ID (e.g. "1.249508314") from a market URL.
 * Returns null if no `1.<digits>` segment is found.
 */
fun extractRaceId(url: String): String? =
    RACE_ID.find(url)?.groupValues?.get(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceIdParserTest'`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RaceIdParser.kt src/test/kotlin/com/horsey/scraper/RaceIdParserTest.kt
git commit -m "Add extractRaceId() for Betfair market URLs"
```

---

## Task 4: Off-time builder

Pure function: build an ISO-8601 off-time string from `HH:mm` + a date + a zone.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/OffTimeBuilder.kt`
- Create: `src/test/kotlin/com/horsey/scraper/OffTimeBuilderTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/OffTimeBuilderTest.kt`:

```kotlin
package com.horsey.scraper

import java.time.LocalDate
import java.time.ZoneId
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class OffTimeBuilderTest {
    private val london = ZoneId.of("Europe/London")

    @Test
    fun `builds BST off-time during summer`() {
        val date = LocalDate.of(2026, 5, 9)
        assertEquals("2026-05-09T13:30:00+01:00", buildOffTime("13:30", date, london))
    }

    @Test
    fun `builds GMT off-time during winter`() {
        val date = LocalDate.of(2026, 1, 15)
        assertEquals("2026-01-15T13:30:00Z", buildOffTime("13:30", date, london))
    }

    @Test
    fun `accepts single-digit hour`() {
        val date = LocalDate.of(2026, 5, 9)
        assertEquals("2026-05-09T09:05:00+01:00", buildOffTime("9:05", date, london))
    }

    @Test
    fun `returns null on malformed input`() {
        val date = LocalDate.of(2026, 5, 9)
        assertNull(buildOffTime("not-a-time", date, london))
        assertNull(buildOffTime("25:00", date, london))
        assertNull(buildOffTime("", date, london))
    }
}
```

Note on the GMT case: `DateTimeFormatter.ISO_OFFSET_DATE_TIME` renders a `+00:00` offset as `Z`. Both forms are valid ISO-8601 and the spec accepts either; we prefer `Z` because that's what Java's default rendering gives us.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.OffTimeBuilderTest'`
Expected: FAIL with `unresolved reference: buildOffTime`.

- [ ] **Step 3: Implement**

Create `src/main/kotlin/com/horsey/scraper/OffTimeBuilder.kt`:

```kotlin
package com.horsey.scraper

import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val HHMM = Regex("""^(\d{1,2}):(\d{2})$""")

/**
 * Builds an ISO-8601 timestamp string with offset for a race off-time.
 *
 * Combines `hhmm` (e.g. "13:30" or "9:05") with `date` interpreted in `zone`
 * to produce a string like "2026-05-09T13:30:00+01:00" (BST) or
 * "2026-01-15T13:30:00Z" (GMT).
 *
 * Returns null on malformed input.
 */
fun buildOffTime(hhmm: String, date: LocalDate, zone: ZoneId): String? {
    val match = HHMM.matchEntire(hhmm) ?: return null
    val hour = match.groupValues[1].toInt()
    val minute = match.groupValues[2].toInt()
    if (hour !in 0..23 || minute !in 0..59) return null
    val time = LocalTime.of(hour, minute)
    val zoned = date.atTime(time).atZone(zone)
    return zoned.toOffsetDateTime().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.OffTimeBuilderTest'`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/OffTimeBuilder.kt src/test/kotlin/com/horsey/scraper/OffTimeBuilderTest.kt
git commit -m "Add buildOffTime() for HH:mm + date + zone -> ISO-8601"
```

---

## Task 5: New data models

Replace the existing models with the multi-market shape. Old `Horse` data class is deleted (it served only the old single-price-per-runner shape). Verify with a Gson round-trip test that the JSON shape exactly matches the spec.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Models.kt`
- Create: `src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt`

- [ ] **Step 1: Write the failing serialization test**

Create `src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.Gson
import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals

class ModelsJsonTest {
    private val gson = Gson()

    @Test
    fun `RaceOdds serializes with flat race fields and pivoted runners`() {
        val odds = RaceOdds(
            raceId = "1.249508314",
            venue = "Lingfield",
            country = "GB",
            offTime = "2026-05-09T13:30:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
            marketName = "13:30 Lingfield - 5f Hcap",
            marketScrapedAt = linkedMapOf(
                MarketType.WIN to "2026-05-09T12:00:04Z",
                MarketType.TOP_3 to "2026-05-09T12:00:11Z"
            ),
            runners = listOf(
                RunnerOdds(
                    name = "Some Horse",
                    lay = linkedMapOf(MarketType.WIN to 4.8, MarketType.TOP_3 to 1.7)
                )
            )
        )

        val expected = """
            {
              "raceId": "1.249508314",
              "venue": "Lingfield",
              "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z", "TOP_3": "2026-05-09T12:00:11Z" },
              "runners": [
                { "name": "Some Horse", "lay": { "WIN": 4.8, "TOP_3": 1.7 } }
              ]
            }
        """.trimIndent()

        assertEquals(JsonParser.parseString(expected), JsonParser.parseString(gson.toJson(odds)))
    }

    @Test
    fun `ScrapeOutput serializes with scrapedAt, raceCount, races`() {
        val output = ScrapeOutput(
            scrapedAt = "2026-05-09T12:00:00Z",
            raceCount = 0,
            races = emptyList()
        )
        val expected = """{"scrapedAt":"2026-05-09T12:00:00Z","raceCount":0,"races":[]}"""
        assertEquals(JsonParser.parseString(expected), JsonParser.parseString(gson.toJson(output)))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew test --tests 'com.horsey.scraper.ModelsJsonTest'`
Expected: FAIL with unresolved references to `RaceOdds`, `RunnerOdds`, `ScrapeOutput`, or constructor mismatch (because the existing `RaceOdds` has the old shape).

- [ ] **Step 3: Replace Models.kt**

Replace the entire contents of `src/main/kotlin/com/horsey/scraper/Models.kt` with:

```kotlin
package com.horsey.scraper

enum class MarketType { WIN, TOP_2, TOP_3, TOP_4, TOP_5 }

/**
 * Race metadata produced by the race-list scraper. Internal type — not
 * serialised directly; its fields are flattened into [RaceOdds] for output.
 */
data class Race(
    val raceId: String,
    val venue: String,
    val country: String,    // "GB" | "IE"
    val offTime: String,    // ISO-8601 with offset
    val winMarketUrl: String
)

/**
 * Result of scraping a single market within a race. Intermediate type
 * passed from per-market scrape into the pivot. Not serialised.
 *
 * `scrapedAt` is an ISO-8601 UTC instant (e.g. "2026-05-09T12:00:04Z").
 * `runners` preserves market-page order; the second element of each
 * pair is the best lay or null if no lay is on offer.
 */
data class MarketScrape(
    val type: MarketType,
    val scrapedAt: String,
    val runners: List<Pair<String, Double?>>
)

/**
 * One runner's lay prices pivoted across markets. Key presence in `lay`
 * mirrors key presence in [RaceOdds.marketScrapedAt]: present iff the
 * market was scraped successfully.
 */
data class RunnerOdds(
    val name: String,
    val lay: Map<MarketType, Double?>
)

/**
 * One race's serialised output. Race fields are flattened (no nested
 * `race` object) so the JSON matches the spec example exactly.
 */
data class RaceOdds(
    val raceId: String,
    val venue: String,
    val country: String,
    val offTime: String,
    val winMarketUrl: String,
    val marketName: String,
    val marketScrapedAt: Map<MarketType, String>,
    val runners: List<RunnerOdds>
)

/**
 * Top-level wrapper for `data.json`.
 * `scrapedAt` is an ISO-8601 UTC instant for the run start.
 * `raceCount == races.size`; races with no successful WIN scrape are dropped.
 */
data class ScrapeOutput(
    val scrapedAt: String,
    val raceCount: Int,
    val races: List<RaceOdds>
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./gradlew test --tests 'com.horsey.scraper.ModelsJsonTest'`
Expected: 2 tests PASS.

- [ ] **Step 5: Stub broken consumers so the project compiles**

After Step 4, four files reference the old shapes (`Race(... url ...)`, `Horse`, `RaceOdds.horses`, `Race.time`) and won't compile:

- `Main.kt` (rewritten in Task 12)
- `TestRaceMain.kt` (uses old `Race(venue, country, time, url)` and `odds.horses` / `odds.marketName`)
- `TestListMain.kt` (uses `it.time` and `it.url`)
- `BetfairRaceListScraper.kt` (rewritten in Task 6, builds `Race(venue=, country=, time=, url=)`)
- `BetfairRaceScraper.kt` (rewritten in Task 11, builds the old `RaceOdds` and `Horse`)

`DebugListMain.kt` does not touch the data classes — leave it alone.

Stub the four broken `main`-class files now so `./gradlew compileKotlin` passes. Replace the body of `Main.kt`'s `main()` with:

```kotlin
fun main() {
    TODO("rewired in Task 12")
}
```

Replace the body of `TestRaceMain.kt`'s `main()` with:

```kotlin
fun main() {
    TODO("rewired in Task 11")
}
```

Replace the body of `TestListMain.kt`'s `main()` with:

```kotlin
fun main() {
    TODO("update for new Race fields after Task 6")
}
```

For `BetfairRaceListScraper.kt` and `BetfairRaceScraper.kt`: leave them broken for now — they'll be rewritten in full in Tasks 6 and 11. To get a clean compile, replace each file's contents with a one-line stub:

```kotlin
package com.horsey.scraper
class BetfairRaceListScraper { fun scrape(): List<Race> = TODO("rewritten in Task 6") }
```

```kotlin
package com.horsey.scraper
class BetfairRaceScraper(private val race: Race) { fun scrape(): RaceOdds? = TODO("rewritten in Task 11") }
```

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 6: Run the model tests**

Run: `./gradlew test --tests 'com.horsey.scraper.ModelsJsonTest'`
Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Models.kt \
        src/test/kotlin/com/horsey/scraper/ModelsJsonTest.kt \
        src/main/kotlin/com/horsey/scraper/Main.kt \
        src/main/kotlin/com/horsey/scraper/TestRaceMain.kt \
        src/main/kotlin/com/horsey/scraper/TestListMain.kt \
        src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt \
        src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt
git commit -m "Reshape data models for multi-market lay-price pivot (consumers stubbed)"
```

---

## Task 6: BetfairRaceListScraper — populate raceId + offTime

Refactor the JS-output-to-Race assembly into a pure function so it can be tested without a browser.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt`
- Create: `src/test/kotlin/com/horsey/scraper/BetfairRaceListScraperTest.kt`

- [ ] **Step 1: Write the failing test**

Create `src/test/kotlin/com/horsey/scraper/BetfairRaceListScraperTest.kt`:

```kotlin
package com.horsey.scraper

import java.time.LocalDate
import java.time.ZoneId
import kotlin.test.Test
import kotlin.test.assertEquals

class BetfairRaceListScraperTest {
    private val london = ZoneId.of("Europe/London")
    private val today = LocalDate.of(2026, 5, 9)

    @Test
    fun `assembles Race objects with raceId and ISO offTime`() {
        val raw = listOf(
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        )
        val races = assembleRaces(raw, today, london)
        assertEquals(1, races.size)
        val r = races.single()
        assertEquals("1.249508314", r.raceId)
        assertEquals("Lingfield", r.venue)
        assertEquals("GB", r.country)
        assertEquals("2026-05-09T13:30:00+01:00", r.offTime)
        assertEquals("https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314", r.winMarketUrl)
    }

    @Test
    fun `skips lines for unknown venues`() {
        val raw = listOf(
            "Bogusville|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `skips lines with unparseable race id`() {
        val raw = listOf(
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `skips lines with unparseable time`() {
        val raw = listOf(
            "Lingfield|||not-a-time|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `dedupes by raceId and sorts by time then venue`() {
        val raw = listOf(
            "Naas|||14:00|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.222",
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111",
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
        )
        val ids = assembleRaces(raw, today, london).map { it.raceId }
        assertEquals(listOf("1.111", "1.222"), ids)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairRaceListScraperTest'`
Expected: FAIL with `unresolved reference: assembleRaces`.

- [ ] **Step 3: Refactor the scraper to expose `assembleRaces`**

Replace the entire contents of `src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt` with:

```kotlin
package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver
import java.time.LocalDate
import java.time.ZoneId

private val LONDON = ZoneId.of("Europe/London")

/**
 * Assembles [Race]s from raw "venue|||hhmm|||href" lines. Pure: no DOM, no
 * clock. Filters out unknown venues, lines with no parseable race ID, and
 * lines with unparseable times. Dedupes by raceId and sorts by offTime
 * then venue.
 */
fun assembleRaces(rawLines: List<String>, today: LocalDate, zone: ZoneId): List<Race> {
    val races = rawLines.mapNotNull { line ->
        val parts = line.split("|||")
        if (parts.size != 3) return@mapNotNull null
        val (venue, hhmm, href) = Triple(parts[0], parts[1], parts[2])
        val country = Venues.countryFor(venue) ?: run {
            System.err.println("Skipping unknown venue: '$venue' ($hhmm)")
            return@mapNotNull null
        }
        val raceId = extractRaceId(href) ?: return@mapNotNull null
        val offTime = buildOffTime(hhmm, today, zone) ?: return@mapNotNull null
        Race(raceId = raceId, venue = venue, country = country, offTime = offTime, winMarketUrl = href)
    }
    return races.distinctBy { it.raceId }.sortedWith(compareBy({ it.offTime }, { it.venue }))
}

/**
 * Scrapes the Betfair Exchange "Today's Racing" landing page for the GB & IE
 * meetings shown on the default tab.
 *
 * DOM shape (as of 2026-05):
 *   ul.country-tabs-container
 *     li.country-tab.active     <-- GB & IE tab is default-active
 *   div.country-content
 *     li.meeting-item
 *       .meeting-info .meeting-label          <-- venue ("Southwell")
 *       ul.race-list li.race-information
 *         a.race-link[href="horse-racing/market/1.NNN"]
 *           span.label                         <-- HH:mm
 */
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7"
) {
    fun scrape(): List<Race> {
        val driver: WebDriver = createChromeDriver()
        try {
            driver.get(url)
            val js = driver as JavascriptExecutor
            val ready = waitForMeetings(driver)
            if (!ready) {
                dumpDiagnostics(js)
                return emptyList()
            }

            ensureGbIeTabActive(driver)
            Thread.sleep(800)
            val raw = extractRawMeetings(js)
            return assembleRaces(raw, LocalDate.now(LONDON), LONDON)
        } finally {
            driver.quit()
        }
    }

    private fun waitForMeetings(driver: WebDriver): Boolean {
        val deadline = System.currentTimeMillis() + 30_000L
        while (System.currentTimeMillis() < deadline) {
            val n = driver.findElements(By.cssSelector("li.meeting-item")).size
            if (n > 0) {
                Thread.sleep(700)
                return true
            }
            Thread.sleep(500)
        }
        return false
    }

    private fun dumpDiagnostics(js: JavascriptExecutor) {
        try {
            val info = js.executeScript("""
                return JSON.stringify({
                    title: document.title,
                    url: location.href,
                    bodyLen: (document.body && document.body.innerText || '').length,
                    meetingItems: document.querySelectorAll('li.meeting-item').length,
                    raceLinks: document.querySelectorAll('a.race-link').length,
                    countryTabs: document.querySelectorAll('li.country-tab').length,
                    activeTab: (document.querySelector('li.country-tab.active .country-label') || {}).textContent || ''
                });
            """) as String
            System.err.println("List page diagnostics: $info")
        } catch (e: Exception) {
            System.err.println("Diagnostics failed: ${e.message}")
        }
    }

    private fun ensureGbIeTabActive(driver: WebDriver) {
        try {
            val tabs = driver.findElements(By.cssSelector("li.country-tab"))
            for (tab in tabs) {
                val flagsHtml = tab.getAttribute("innerHTML") ?: ""
                if (flagsHtml.contains("country-flags-gb") && flagsHtml.contains("country-flags-ie")) {
                    val classAttr = tab.getAttribute("class") ?: ""
                    if (!classAttr.contains("active")) {
                        tab.click()
                        Thread.sleep(700)
                    }
                    return
                }
            }
        } catch (e: Exception) {
            // Tab structure may differ when only one country has races.
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun extractRawMeetings(js: JavascriptExecutor): List<String> {
        return js.executeScript("""
            var out = [];
            var meetings = document.querySelectorAll('li.meeting-item');
            for (var i = 0; i < meetings.length; i++) {
                var meetingEl = meetings[i];
                var labelEl = meetingEl.querySelector('.meeting-label');
                if (!labelEl) continue;
                var venue = (labelEl.textContent || '').trim();
                if (!venue) continue;

                var raceLinks = meetingEl.querySelectorAll('a.race-link');
                for (var r = 0; r < raceLinks.length; r++) {
                    var a = raceLinks[r];
                    var labelSpan = a.querySelector('span.label');
                    var time = labelSpan ? (labelSpan.textContent || '').trim()
                                         : (a.textContent || '').trim();
                    var timeMatch = time.match(/\d{1,2}:\d{2}/);
                    if (!timeMatch) continue;
                    out.push(venue + '|||' + timeMatch[0] + '|||' + a.href);
                }
            }
            return out;
        """) as? List<String> ?: emptyList()
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairRaceListScraperTest'`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt src/test/kotlin/com/horsey/scraper/BetfairRaceListScraperTest.kt
git commit -m "Refactor race-list scraper: pure assembleRaces() with raceId + offTime"
```

---

## Task 7: Runner pivot

Pure function: take a `Map<MarketType, MarketScrape>` (only successful scrapes present) and a list of Win runner names, produce `List<RunnerOdds>` with key-presence parity. Drop phantoms (in Top-N but not in Win) with a stderr warning.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RunnerPivot.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt`:

```kotlin
package com.horsey.scraper

import java.io.ByteArrayOutputStream
import java.io.PrintStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RunnerPivotTest {
    private fun captureStderr(block: () -> Unit): String {
        val buf = ByteArrayOutputStream()
        val original = System.err
        System.setErr(PrintStream(buf))
        try {
            block()
        } finally {
            System.setErr(original)
        }
        return buf.toString()
    }

    @Test
    fun `pivots runners across all five markets`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf("Some Horse" to 4.8, "Outsider" to 22.0))
        val top2 = MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z",
            listOf("Some Horse" to 2.5, "Outsider" to 9.5))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("Some Horse" to 1.7, "Outsider" to 5.0))
        val top4 = MarketScrape(MarketType.TOP_4, "2026-05-09T12:00:14Z",
            listOf("Some Horse" to 1.4, "Outsider" to 3.2))
        val top5 = MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z",
            listOf("Some Horse" to 1.2, "Outsider" to 2.4))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(
                MarketType.WIN to win, MarketType.TOP_2 to top2, MarketType.TOP_3 to top3,
                MarketType.TOP_4 to top4, MarketType.TOP_5 to top5
            ),
            raceIdForWarnings = "1.111"
        )

        assertEquals(2, runners.size)
        assertEquals("Some Horse", runners[0].name)
        assertEquals(
            mapOf(MarketType.WIN to 4.8, MarketType.TOP_2 to 2.5, MarketType.TOP_3 to 1.7,
                  MarketType.TOP_4 to 1.4, MarketType.TOP_5 to 1.2),
            runners[0].lay
        )
    }

    @Test
    fun `omits keys for markets that were not scraped`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to 1.5))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )

        assertEquals(1, runners.size)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), runners[0].lay.keys)
    }

    @Test
    fun `preserves null lay for runner with no offer in a scraped market`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to null))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        assertEquals(mapOf(MarketType.WIN to 3.0, MarketType.TOP_3 to null), runners[0].lay)
    }

    @Test
    fun `runner missing from a scraped Top-N market gets null for that key`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf("X" to 3.0, "Y" to 10.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("X" to 1.5))  // Y missing

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        val y = runners.single { it.name == "Y" }
        assertEquals(mapOf(MarketType.WIN to 10.0, MarketType.TOP_3 to null), y.lay)
    }

    @Test
    fun `phantom horse in Top-N is dropped with stderr warning`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("X" to 1.5, "Phantom" to 7.0))

        var runners: List<RunnerOdds> = emptyList()
        val stderr = captureStderr {
            runners = pivotMarketScrapes(
                scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
                raceIdForWarnings = "1.111"
            )
        }
        assertEquals(listOf("X"), runners.map { it.name })
        assertTrue("Phantom horse 'Phantom' in TOP_3 for race 1.111 — dropping" in stderr,
            "stderr was: $stderr")
    }

    @Test
    fun `returns empty list when WIN scrape is absent`() {
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to 1.5))
        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        assertEquals(emptyList(), runners)
    }

    @Test
    fun `lay map preserves MarketType declared order`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top5 = MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z", listOf("X" to 1.1))
        val top2 = MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z", listOf("X" to 2.0))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.TOP_5 to top5, MarketType.WIN to win, MarketType.TOP_2 to top2),
            raceIdForWarnings = "1.111"
        )
        assertEquals(listOf(MarketType.WIN, MarketType.TOP_2, MarketType.TOP_5),
            runners[0].lay.keys.toList())
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RunnerPivotTest'`
Expected: FAIL with `unresolved reference: pivotMarketScrapes`.

- [ ] **Step 3: Implement**

Create `src/main/kotlin/com/horsey/scraper/RunnerPivot.kt`:

```kotlin
package com.horsey.scraper

/**
 * Combines per-market scrapes into a per-runner pivot.
 *
 * Rules (see spec, "Edge-case rules"):
 *   - WIN absent → returns empty list (no runner source of truth).
 *   - Each runner's lay map has exactly the keys present in `scrapes`.
 *   - Runner not seen in some scraped market → that key maps to null.
 *   - Runner appearing in Top-N but not WIN → dropped, stderr warning.
 *   - Result preserves MarketType declared order in each runner's lay map
 *     and Win-page order in the runners list.
 */
fun pivotMarketScrapes(
    scrapes: Map<MarketType, MarketScrape>,
    raceIdForWarnings: String
): List<RunnerOdds> {
    val win = scrapes[MarketType.WIN] ?: return emptyList()

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
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RunnerPivotTest'`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RunnerPivot.kt src/test/kotlin/com/horsey/scraper/RunnerPivotTest.kt
git commit -m "Add pivotMarketScrapes() with phantom-horse drop + warn"
```

---

## Task 8: Spike — discover related-markets DOM

Investigative task. Build a small entry-point that loads one Win market URL and dumps everything that could plausibly be a related-market link. Read the output and document what we find.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/DebugMarketLinks.kt`

- [ ] **Step 1: Write the dumper**

Create `src/main/kotlin/com/horsey/scraper/DebugMarketLinks.kt`:

```kotlin
package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor

/**
 * Spike: load a Win market URL (passed as the first arg, or default below)
 * and dump everything that could be a related-market link. Read the output
 * and use it to write the selectors used in RelatedMarketsFinder.
 *
 * Run with:
 *   ./gradlew run -PmainClass=com.horsey.scraper.DebugMarketLinksKt --args='https://www.betfair.com/exchange/plus/en/horse-racing/market/1.NNN'
 *
 * Or, after a real run of Main, copy any race URL from data.json.
 */
fun main(args: Array<String>) {
    val url = args.firstOrNull() ?: error(
        "Pass a Win market URL as the first argument, e.g. " +
        "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
    )
    val driver = createChromeDriver()
    try {
        driver.get(url)
        Thread.sleep(8000)  // crude wait for SPA to settle
        val js = driver as JavascriptExecutor

        @Suppress("UNCHECKED_CAST")
        val report = js.executeScript("""
            function dump(selector) {
                var rows = [];
                document.querySelectorAll(selector).forEach(function(el) {
                    var t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
                    var href = el.getAttribute('href') || '';
                    var cls = el.getAttribute('class') || '';
                    rows.push(selector + ' | text="' + t + '" | href="' + href + '" | class="' + cls + '"');
                });
                return rows;
            }
            var out = [];
            // Likely places: sidebar nav, market-tabs, dropdowns
            ['a[href*="/market/1."]', 'li.market-item', 'a.market-link',
             '.market-list a', '.related-markets a', 'nav a',
             '[class*="market"] a'].forEach(function(sel) {
                out = out.concat(dump(sel));
            });
            // Anything containing "Top" or "To Be Placed" anywhere
            document.querySelectorAll('a, button, li').forEach(function(el) {
                var t = (el.textContent || '').trim();
                if (/^Top \d+ /.test(t) || /^To Be Placed/i.test(t)) {
                    out.push('TEXT-MATCH | tag=' + el.tagName + ' | text="' + t.slice(0,60) +
                             '" | href="' + (el.getAttribute('href') || '') +
                             '" | class="' + (el.getAttribute('class') || '') + '"');
                }
            });
            return out;
        """) as List<String>

        println("==== Related-markets dump for $url ====")
        report.forEach(::println)
        println("==== ${report.size} candidate elements ====")
    } finally {
        driver.quit()
    }
}
```

- [ ] **Step 2: Run it**

First obtain a current Win market URL: open `https://www.betfair.com/exchange/plus/en/horse-racing-betting-7` in your browser, click any race, and copy the URL from the address bar. It will look like `https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314`.

Then run:

```bash
./gradlew run -PmainClass=com.horsey.scraper.DebugMarketLinksKt --args='https://www.betfair.com/exchange/plus/en/horse-racing/market/1.NNN' --quiet
```

Expected: console dumps a list of candidate elements. Look for entries whose text is exactly `Top 2 Finish`, `Top 3 Finish`, `Top 4 Finish`, `Top 5 Finish`, and note the `href` (which `1.NNN` they point to) and the `class` attribute of the surrounding element.

If the spike returns nothing useful (e.g. Betfair gates these markets behind a login or a different page section), pause and tell the user — we'll need to revise the discovery approach before continuing with Task 9.

- [ ] **Step 3: Document findings**

Add a comment block at the top of `DebugMarketLinks.kt` (after the existing top-of-file comment) recording what you observed, e.g.:

```kotlin
// Findings from 2026-05-09 dump:
//   Selector that hit: <write the actual selector you saw>
//   Each Top-N link was an <a> with text exactly "Top 2 Finish", "Top 3 Finish", etc.
//   href shape: <write the actual URL pattern>
```

These notes are what Task 9 reads to write its selector.

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/DebugMarketLinks.kt
git commit -m "Add DebugMarketLinks spike for related-markets DOM discovery"
```

---

## Task 9: Related-markets finder

Use the selector discovered in Task 8 to find the four Top-N market URLs from a loaded Win page.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RelatedMarketsFinder.kt`

- [ ] **Step 1: Implement using the discovered selector**

Create `src/main/kotlin/com/horsey/scraper/RelatedMarketsFinder.kt`. The function below uses a defensive **text-match** approach (matching on the visible link text "Top 2 Finish" etc.) because that's much more stable than guessing class names. Replace the inner JS with the more specific selector you discovered in Task 8 if it's reliable; otherwise keep the text-match fallback as a second pass.

```kotlin
package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver

/**
 * Finds Top-N market URLs in the currently-loaded race page DOM.
 *
 * Returns a map containing entries only for markets actually present on the
 * page. Missing markets (e.g. TOP_5 absent for a small field) result in
 * absent keys, which is exactly what the rest of the pipeline expects.
 *
 * Strategy: walk every <a> on the page and match link text against
 * "Top 2 Finish", "Top 3 Finish", etc. This is more resilient to
 * Betfair restyling its sidebar than a class-name selector would be.
 *
 * Reads `driver`'s current page; does not navigate.
 */
fun findTopNUrls(driver: WebDriver): Map<MarketType, String> {
    val js = driver as JavascriptExecutor

    @Suppress("UNCHECKED_CAST")
    val raw = js.executeScript("""
        var wanted = { 'Top 2 Finish':'TOP_2', 'Top 3 Finish':'TOP_3',
                       'Top 4 Finish':'TOP_4', 'Top 5 Finish':'TOP_5' };
        var out = [];
        document.querySelectorAll('a').forEach(function(a) {
            var t = (a.textContent || '').trim();
            if (wanted.hasOwnProperty(t)) {
                var href = a.href || '';
                if (href && /\/market\/1\./.test(href)) {
                    out.push(wanted[t] + '|||' + href);
                }
            }
        });
        return out;
    """) as? List<String> ?: emptyList()

    val result = linkedMapOf<MarketType, String>()
    for (line in raw) {
        val parts = line.split("|||", limit = 2)
        if (parts.size != 2) continue
        val type = runCatching { MarketType.valueOf(parts[0]) }.getOrNull() ?: continue
        // First occurrence wins; sidebars sometimes duplicate in mobile nav etc.
        result.putIfAbsent(type, parts[1])
    }
    return result
}
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL` (the broken consumers in `Main.kt` etc. are stubbed; this file compiles cleanly).

We don't add a unit test here — the function is a thin wrapper over a live DOM. It's verified via the smoke run in Task 13.

- [ ] **Step 3: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RelatedMarketsFinder.kt
git commit -m "Add findTopNUrls() reading Top-N links from race page DOM"
```

---

## Task 10: Single-market scraper

Factor the per-market scrape (page wait + JS extraction of `(name, layPrice)` pairs) out of the existing `BetfairRaceScraper` so it can be reused for Win and Top-N alike.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/MarketScraper.kt`

- [ ] **Step 1: Implement**

Create `src/main/kotlin/com/horsey/scraper/MarketScraper.kt`:

```kotlin
package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver
import org.openqa.selenium.WebElement
import org.openqa.selenium.support.ui.ExpectedConditions
import org.openqa.selenium.support.ui.WebDriverWait
import java.time.Duration
import java.time.Instant

/**
 * Scrapes a single Betfair Exchange market page that is already loaded in
 * `driver`. Returns a [MarketScrape] with one entry per visible runner; the
 * lay value is null where no lay is currently on offer.
 *
 * Caller is responsible for navigating `driver` to the market URL before
 * calling this. We wait up to 20s for runner rows to appear.
 *
 * For markets with many runners, a virtual-scroll loop walks the runner list
 * to pick up entries beyond the initial viewport. Most horse races finish in
 * one pass; the loop is harmless when nothing scrolls.
 */
fun scrapeLoadedMarket(driver: WebDriver, type: MarketType): MarketScrape {
    waitForRunners(driver)
    val runners = scrollAndExtract(driver as JavascriptExecutor)
    return MarketScrape(
        type = type,
        scrapedAt = Instant.now().toString(),
        runners = runners
    )
}

private fun waitForRunners(driver: WebDriver) {
    val wait = WebDriverWait(driver, Duration.ofSeconds(20))
    wait.until(
        ExpectedConditions.presenceOfElementLocated(By.cssSelector("tr.runner-line, h3.runner-name"))
    )
    Thread.sleep(2000)
}

private fun scrollAndExtract(js: JavascriptExecutor): List<Pair<String, Double?>> {
    val map = linkedMapOf<String, Double?>()
    val scrollContainer = findScrollableContainer(js)
    if (scrollContainer == null) {
        collectVisible(js, map)
        return map.toList()
    }

    val clientHeight = js.executeScript("return arguments[0].clientHeight;", scrollContainer) as Long
    js.executeScript("arguments[0].scrollTop = 0;", scrollContainer)
    Thread.sleep(400)

    var noNewCount = 0
    while (noNewCount < 6) {
        val previousSize = map.size
        collectVisible(js, map)
        if (map.size > previousSize) noNewCount = 0 else noNewCount++

        js.executeScript(
            "arguments[0].scrollTop += arguments[1];",
            scrollContainer,
            (clientHeight * 0.6).toLong()
        )
        Thread.sleep(500)

        val atBottom = js.executeScript(
            "var el = arguments[0]; return el.scrollTop + el.clientHeight >= el.scrollHeight - 5;",
            scrollContainer
        ) as Boolean
        if (atBottom) {
            collectVisible(js, map)
            break
        }
    }
    return map.toList()
}

private fun findScrollableContainer(js: JavascriptExecutor): WebElement? {
    return try {
        js.executeScript("""
            var runner = document.querySelector('h3.runner-name');
            if (runner) {
                var el = runner.parentElement;
                while (el && el !== document.body && el !== document.documentElement) {
                    var style = window.getComputedStyle(el);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 20) {
                        return el;
                    }
                    el = el.parentElement;
                }
            }
            return null;
        """) as? WebElement
    } catch (e: Exception) {
        null
    }
}

@Suppress("UNCHECKED_CAST")
private fun collectVisible(js: JavascriptExecutor, into: MutableMap<String, Double?>) {
    try {
        val results = js.executeScript("""
            var out = [];
            var rows = document.querySelectorAll('tr.runner-line');
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var nameEl = row.querySelector('h3.runner-name');
                if (!nameEl) continue;
                var name = nameEl.textContent.trim();
                if (!name) continue;

                var price = '';
                var layCell = row.querySelector('td.first-lay-cell');
                if (layCell) {
                    var label = layCell.querySelector('label');
                    if (label) {
                        var t = (label.textContent || '').trim();
                        var n = parseFloat(t);
                        if (!isNaN(n) && n > 1) price = t;
                    }
                }
                out.push(name + '|||' + price);
            }
            return out;
        """) as? List<String> ?: return

        for (item in results) {
            val parts = item.split("|||")
            if (parts.isEmpty()) continue
            val name = parts[0]
            if (name.isBlank()) continue
            val price = parts.getOrNull(1)?.toDoubleOrNull()
            if (!into.containsKey(name)) {
                into[name] = price
            } else if (into[name] == null && price != null) {
                into[name] = price
            }
        }
    } catch (e: Exception) {
        // Soft-fail: missed snapshots are recovered by subsequent scroll passes.
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/MarketScraper.kt
git commit -m "Extract scrapeLoadedMarket() reusable across WIN + Top-N markets"
```

---

## Task 11: Refactor BetfairRaceScraper for multi-market

Orchestrate one Chrome per race: load Win, scrape it, find Top-N URLs, navigate to each in turn, scrape, then pivot.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt`
- Create: `src/test/kotlin/com/horsey/scraper/BetfairRaceScraperAssemblyTest.kt`

- [ ] **Step 1: Write the failing test for the pure assembler**

Create `src/test/kotlin/com/horsey/scraper/BetfairRaceScraperAssemblyTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class BetfairRaceScraperAssemblyTest {
    private val race = Race(
        raceId = "1.111", venue = "Lingfield", country = "GB",
        offTime = "2026-05-09T13:30:00+01:00",
        winMarketUrl = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
    )

    @Test
    fun `assembleRaceOdds produces flat fields and pivot`() {
        val scrapes = mapOf(
            MarketType.WIN to MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
                listOf("X" to 3.0)),
            MarketType.TOP_3 to MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
                listOf("X" to 1.5))
        )
        val odds = assembleRaceOdds(race, "13:30 Lingfield - 5f Hcap", scrapes)
        assertEquals(race.raceId, odds!!.raceId)
        assertEquals("Lingfield", odds.venue)
        assertEquals("GB", odds.country)
        assertEquals(race.offTime, odds.offTime)
        assertEquals(race.winMarketUrl, odds.winMarketUrl)
        assertEquals("13:30 Lingfield - 5f Hcap", odds.marketName)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), odds.marketScrapedAt.keys)
        assertEquals(1, odds.runners.size)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), odds.runners[0].lay.keys)
    }

    @Test
    fun `assembleRaceOdds returns null when WIN scrape is missing`() {
        val scrapes = mapOf(
            MarketType.TOP_3 to MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
                listOf("X" to 1.5))
        )
        assertNull(assembleRaceOdds(race, "irrelevant", scrapes))
    }

    @Test
    fun `marketScrapedAt preserves MarketType declared order`() {
        val scrapes = mapOf(
            MarketType.TOP_5 to MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z",
                listOf("X" to 1.1)),
            MarketType.WIN to MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
                listOf("X" to 3.0)),
            MarketType.TOP_2 to MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z",
                listOf("X" to 2.0))
        )
        val odds = assembleRaceOdds(race, "x", scrapes)
        assertEquals(listOf(MarketType.WIN, MarketType.TOP_2, MarketType.TOP_5),
            odds!!.marketScrapedAt.keys.toList())
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairRaceScraperAssemblyTest'`
Expected: FAIL with `unresolved reference: assembleRaceOdds`.

- [ ] **Step 3: Replace BetfairRaceScraper.kt**

Replace the entire contents of `src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt` with:

```kotlin
package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.WebDriver

private const val TOP_N_TYPES_COUNT = 4
private const val INTER_MARKET_DELAY_MS = 500L

/**
 * Pure assembler: combines a [Race], a market name, and a per-market scrape
 * map into a [RaceOdds] for output. Returns null when the WIN scrape is
 * absent (per spec rule 7: race with no Win is omitted).
 */
fun assembleRaceOdds(
    race: Race,
    marketName: String,
    scrapes: Map<MarketType, MarketScrape>
): RaceOdds? {
    if (MarketType.WIN !in scrapes) return null

    val orderedTypes = MarketType.values().filter { it in scrapes }
    val marketScrapedAt = linkedMapOf<MarketType, String>()
    for (type in orderedTypes) {
        marketScrapedAt[type] = scrapes.getValue(type).scrapedAt
    }
    val runners = pivotMarketScrapes(scrapes, raceIdForWarnings = race.raceId)

    return RaceOdds(
        raceId = race.raceId,
        venue = race.venue,
        country = race.country,
        offTime = race.offTime,
        winMarketUrl = race.winMarketUrl,
        marketName = marketName,
        marketScrapedAt = marketScrapedAt,
        runners = runners
    )
}

/**
 * Scrapes one race across WIN + Top 2/3/4/5 Finish in a single Chrome
 * session. Returns null if the Win scrape failed (per spec rule 7).
 *
 * Failures of individual Top-N markets are caught and produce key-omitted
 * semantics in the output (per spec rules 2 & 3).
 */
class BetfairRaceScraper(private val race: Race) {
    fun scrape(): RaceOdds? {
        val driver: WebDriver = createChromeDriver()
        try {
            driver.get(race.winMarketUrl)

            val winScrape = try {
                scrapeLoadedMarket(driver, MarketType.WIN)
            } catch (e: Exception) {
                System.err.println("WIN scrape failed for ${race.raceId}: ${e.message}")
                return null
            }

            val marketName = extractMarketName(driver)
            val scrapes = linkedMapOf(MarketType.WIN to winScrape)

            val topNUrls = try {
                findTopNUrls(driver)
            } catch (e: Exception) {
                System.err.println("Related-markets discovery failed for ${race.raceId}: ${e.message}")
                emptyMap<MarketType, String>()
            }

            for (type in listOf(MarketType.TOP_2, MarketType.TOP_3, MarketType.TOP_4, MarketType.TOP_5)) {
                val url = topNUrls[type] ?: continue  // market not present on page
                Thread.sleep(INTER_MARKET_DELAY_MS)
                try {
                    driver.get(url)
                    scrapes[type] = scrapeLoadedMarket(driver, type)
                } catch (e: Exception) {
                    System.err.println("$type scrape failed for ${race.raceId}: ${e.message}")
                    // Key omitted: do not put into `scrapes`.
                }
            }

            check(scrapes.size <= 1 + TOP_N_TYPES_COUNT) { "more market types than expected" }
            return assembleRaceOdds(race, marketName, scrapes)
        } finally {
            driver.quit()
        }
    }

    private fun extractMarketName(driver: WebDriver): String {
        return try {
            driver.findElement(By.cssSelector("h1")).text.trim()
                .ifEmpty { "${race.offTime} ${race.venue}" }
        } catch (e: Exception) {
            "${race.offTime} ${race.venue}"
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairRaceScraperAssemblyTest'`
Expected: 3 tests PASS.

- [ ] **Step 5: Verify the whole project still compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL` (or the same `Main.kt` errors from Task 5 — fixed in Task 12).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt src/test/kotlin/com/horsey/scraper/BetfairRaceScraperAssemblyTest.kt
git commit -m "Refactor BetfairRaceScraper for multi-market scrape + pivot"
```

---

## Task 12: Update Main.kt

Wire everything together with the new top-level wrapper and ISO-8601 UTC `scrapedAt`.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Replace Main.kt**

Replace the entire contents of `src/main/kotlin/com/horsey/scraper/Main.kt` with:

```kotlin
package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.Instant
import java.util.ArrayDeque

private const val PER_RACE_DELAY_MS = 2_000L
private const val OUTPUT_FILE = "data.json"

/**
 * Entry point: a single pass over today's UK + IE Betfair Exchange races.
 *
 *   1. Reads the race list from the horse-racing landing page.
 *   2. For each race, opens one Chrome and scrapes WIN + Top 2/3/4/5 Finish.
 *   3. Pivots into per-horse lay map and writes data.json.
 *
 * Output schema: see docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md
 */
fun main() {
    val gson = GsonBuilder().setPrettyPrinting().create()

    println("Horsey Scraper — Betfair Exchange (UK + IE) — multi-market lay")
    println("=".repeat(80))

    val runStart = Instant.now()
    println("\n[$runStart] Fetching today's race list…")
    val races = BetfairRaceListScraper().scrape()
    println("Found ${races.size} UK/IE races today.")
    races.forEach { println("  ${it.offTime}  ${it.country}  ${it.venue}  (${it.raceId})") }

    val results = mutableListOf<RaceOdds>()
    if (races.isNotEmpty()) {
        val queue = ArrayDeque(races)
        while (queue.isNotEmpty()) {
            val race = queue.poll()
            print("Scraping ${race.offTime} ${race.venue} (${race.raceId})… ")
            try {
                val odds = BetfairRaceScraper(race).scrape()
                if (odds == null) {
                    println("DROPPED (no WIN scrape)")
                } else {
                    val markets = odds.marketScrapedAt.keys.joinToString(",") { it.name }
                    println("${odds.runners.size} runners, markets=[$markets]")
                    results.add(odds)
                }
            } catch (e: Exception) {
                println("FAILED: ${e.message}")
            }
            if (queue.isNotEmpty()) Thread.sleep(PER_RACE_DELAY_MS)
        }
    }

    val output = ScrapeOutput(
        scrapedAt = runStart.toString(),
        raceCount = results.size,
        races = results
    )
    File(OUTPUT_FILE).writeText(gson.toJson(output))
    println("\nWrote $OUTPUT_FILE (${results.size} races)")
}
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`. (If the `Test*Main.kt` / `Debug*Main.kt` files were stubbed in Task 5 and still call old APIs, fix them now — for each file, either delete it if it's no longer useful, or rewrite its body to use the new APIs. None of them are required for the feature; they were scratch files.)

- [ ] **Step 3: Run the full test suite**

Run: `./gradlew test`
Expected: All tests pass — `SanityTest`, `MarketTypeTest`, `RaceIdParserTest` (5), `OffTimeBuilderTest` (4), `ModelsJsonTest` (2), `BetfairRaceListScraperTest` (5), `RunnerPivotTest` (7), `BetfairRaceScraperAssemblyTest` (3) — 28 tests total.

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "Wire Main to new ScrapeOutput shape with ISO-8601 UTC scrapedAt"
```

(Add any `Test*Main.kt` / `Debug*Main.kt` you fixed/deleted in Step 2 to this commit too.)

---

## Task 13: Schema validator

Encode the spec's "Acceptance" checks as runnable code so we can verify any `data.json` against the contract without eyeballing it.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/SchemaValidator.kt`
- Create: `src/main/kotlin/com/horsey/scraper/ValidateMain.kt`
- Create: `src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SchemaValidatorTest {
    private val goodJson = """
    {
      "scrapedAt": "2026-05-09T12:00:00Z",
      "raceCount": 1,
      "races": [
        {
          "raceId": "1.249508314",
          "venue": "Lingfield",
          "country": "GB",
          "offTime": "2026-05-09T13:30:00+01:00",
          "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
          "marketName": "13:30 Lingfield - 5f Hcap",
          "marketScrapedAt": {
            "WIN": "2026-05-09T12:00:04Z", "TOP_2": "2026-05-09T12:00:08Z",
            "TOP_3": "2026-05-09T12:00:11Z", "TOP_4": "2026-05-09T12:00:14Z",
            "TOP_5": "2026-05-09T12:00:17Z"
          },
          "runners": [
            { "name": "Some Horse",
              "lay": { "WIN": 4.8, "TOP_2": 2.5, "TOP_3": 1.7, "TOP_4": 1.4, "TOP_5": 1.2 } }
          ]
        }
      ]
    }
    """.trimIndent()

    @Test
    fun `valid full file produces no errors`() {
        assertEquals(emptyList(), validateScrapeOutput(goodJson))
    }

    @Test
    fun `partial markets pass when key parity holds`() {
        val partial = """
        {
          "scrapedAt": "2026-05-09T12:00:00Z",
          "raceCount": 1,
          "races": [
            {
              "raceId": "1.249508314",
              "venue": "Lingfield", "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z", "TOP_3": "2026-05-09T12:00:11Z" },
              "runners": [ { "name": "X", "lay": { "WIN": 4.8, "TOP_3": 1.7 } } ]
            }
          ]
        }
        """.trimIndent()
        assertEquals(emptyList(), validateScrapeOutput(partial))
    }

    @Test
    fun `key parity violation is flagged`() {
        // marketScrapedAt has WIN only, but runner's lay has WIN + TOP_3.
        val bad = """
        {
          "scrapedAt": "2026-05-09T12:00:00Z",
          "raceCount": 1,
          "races": [
            {
              "raceId": "1.249508314",
              "venue": "Lingfield", "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z" },
              "runners": [ { "name": "X", "lay": { "WIN": 4.8, "TOP_3": 1.7 } } ]
            }
          ]
        }
        """.trimIndent()
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("key parity") },
            "errors were: $errors")
    }

    @Test
    fun `bad raceId regex is flagged`() {
        val bad = goodJson.replace(""""raceId": "1.249508314"""", """"raceId": "X.123"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("raceId") }, "errors were: $errors")
    }

    @Test
    fun `bad scrapedAt format is flagged`() {
        val bad = goodJson.replace(""""scrapedAt": "2026-05-09T12:00:00Z"""",
            """"scrapedAt": "yesterday"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("scrapedAt") }, "errors were: $errors")
    }

    @Test
    fun `bad country is flagged`() {
        val bad = goodJson.replace(""""country": "GB"""", """"country": "FR"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("country") }, "errors were: $errors")
    }

    @Test
    fun `bad offTime format is flagged`() {
        val bad = goodJson.replace(
            """"offTime": "2026-05-09T13:30:00+01:00"""",
            """"offTime": "13:30"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("offTime") }, "errors were: $errors")
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.SchemaValidatorTest'`
Expected: FAIL with `unresolved reference: validateScrapeOutput`.

- [ ] **Step 3: Implement the validator**

Create `src/main/kotlin/com/horsey/scraper/SchemaValidator.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.JsonElement
import com.google.gson.JsonParser
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

private val RACE_ID_REGEX = Regex("""^1\.\d+$""")
private val ALLOWED_COUNTRIES = setOf("GB", "IE")
private val ALLOWED_MARKETS = setOf("WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5")

/**
 * Validates a `data.json` payload string against the spec rules.
 * Returns an empty list if the file is valid; otherwise a list of
 * human-readable error descriptions.
 *
 * Encodes the rules in the spec's "Edge-case rules" and "Acceptance" sections.
 */
fun validateScrapeOutput(json: String): List<String> {
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
        if (!raceEl.isJsonObject) {
            errors += "$ctx: not an object"
            return@forEachIndexed
        }
        val race = raceEl.asJsonObject

        requireString(race, "raceId", errors) { v ->
            if (!RACE_ID_REGEX.matches(v)) errors += "$ctx.raceId does not match ^1\\.\\d+$: '$v'"
        }
        requireString(race, "venue", errors)
        requireString(race, "country", errors) { v ->
            if (v !in ALLOWED_COUNTRIES) errors += "$ctx.country not in $ALLOWED_COUNTRIES: '$v'"
        }
        requireString(race, "offTime", errors) { v ->
            if (!isIsoOffsetDateTime(v)) errors += "$ctx.offTime not ISO-8601 with offset: '$v'"
        }
        requireString(race, "winMarketUrl", errors)
        requireString(race, "marketName", errors)

        val msaEl = race.get("marketScrapedAt")
        if (msaEl == null || !msaEl.isJsonObject) {
            errors += "$ctx.marketScrapedAt: missing or not object"
            return@forEachIndexed
        }
        val msa = msaEl.asJsonObject
        val msaKeys = msa.keySet()
        if (msaKeys.isEmpty()) errors += "$ctx.marketScrapedAt: empty (must contain at least WIN)"
        if ("WIN" !in msaKeys) errors += "$ctx.marketScrapedAt: missing required WIN key"
        for (key in msaKeys) {
            if (key !in ALLOWED_MARKETS) errors += "$ctx.marketScrapedAt: unknown market '$key'"
            val v = msa.get(key)?.asString ?: ""
            if (!isIsoUtc(v)) errors += "$ctx.marketScrapedAt.$key not ISO-8601 UTC: '$v'"
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
            val layEl = r.get("lay")
            if (layEl == null || !layEl.isJsonObject) {
                errors += "$rctx.lay: missing or not object"
                return@forEachIndexed
            }
            val layKeys = layEl.asJsonObject.keySet()
            if (layKeys != msaKeys) {
                errors += "$rctx.lay: key parity violation — has $layKeys, marketScrapedAt has $msaKeys"
            }
        }
    }
    return errors
}

private fun requireString(
    obj: com.google.gson.JsonObject,
    key: String,
    errors: MutableList<String>,
    extra: (String) -> Unit = {}
): String? {
    val el: JsonElement? = obj.get(key)
    if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
        errors += "$key: missing or not string"
        return null
    }
    val v = el.asString
    extra(v)
    return v
}

private fun requireInt(
    obj: com.google.gson.JsonObject,
    key: String,
    errors: MutableList<String>
): Int? {
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

Create `src/main/kotlin/com/horsey/scraper/ValidateMain.kt`:

```kotlin
package com.horsey.scraper

import java.io.File
import kotlin.system.exitProcess

/**
 * Entry point: validate a data.json file against the spec.
 *
 * Usage:
 *   ./gradlew run -PmainClass=com.horsey.scraper.ValidateMainKt --args='data.json'
 *
 * Exits with code 0 if valid, 1 if validation errors found, 2 on file error.
 */
fun main(args: Array<String>) {
    val path = args.firstOrNull() ?: "data.json"
    val file = File(path)
    if (!file.exists()) {
        System.err.println("File not found: $path")
        exitProcess(2)
    }
    val errors = validateScrapeOutput(file.readText())
    if (errors.isEmpty()) {
        println("$path: VALID (matches spec)")
        exitProcess(0)
    } else {
        println("$path: INVALID (${errors.size} errors)")
        errors.forEach { println("  - $it") }
        exitProcess(1)
    }
}
```

- [ ] **Step 4: Run validator tests**

Run: `./gradlew test --tests 'com.horsey.scraper.SchemaValidatorTest'`
Expected: 7 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`
Expected: 35 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/SchemaValidator.kt src/main/kotlin/com/horsey/scraper/ValidateMain.kt src/test/kotlin/com/horsey/scraper/SchemaValidatorTest.kt
git commit -m "Add SchemaValidator + ValidateMain to enforce spec rules on data.json"
```

---

## Task 14: End-to-end smoke run

No new code. Run the scraper for real, validate, and eyeball.

- [ ] **Step 1: Run the scraper**

Run: `./run.sh`
Expected: prints found races, then per-race scrape lines (`HH:mm:SS Venue (1.NNN)… N runners, markets=[WIN,TOP_2,TOP_3,TOP_4,TOP_5]`), then `Wrote data.json (N races)`.

If the run is happening outside UK racing hours (most days, 12:00–21:00 UK local), the race list may be empty — that's fine, it still produces a valid empty `data.json`. Re-run during racing hours for a full end-to-end test.

- [ ] **Step 2: Validate the output**

Run: `./gradlew run -PmainClass=com.horsey.scraper.ValidateMainKt --args='data.json' --quiet`
Expected: `data.json: VALID (matches spec)`. Exit code 0.

If errors are reported: read them carefully and fix. Most likely failure modes:
- `key parity violation` → `RelatedMarketsFinder` missed a market the page actually offered, or a Top-N scrape silently produced an empty runner list. Check stderr from the smoke run.
- `offTime not ISO-8601 with offset` → check `OffTimeBuilder` got hit; rare regression.

- [ ] **Step 3: Eyeball one race**

Open `data.json` and pick a race. Open the corresponding `winMarketUrl` in a browser. For 2–3 horses, confirm the WIN lay matches the Betfair UI. Then click through to "Top 3 Finish" (or whichever Top-N markets are in the file) and confirm those lays match too.

If they don't match, the most likely culprits:
- Wrong selector in `MarketScraper.collectVisible` (the `td.first-lay-cell` / `label` chain).
- Stale page after navigation in `BetfairRaceScraper.scrape` — bump `INTER_MARKET_DELAY_MS` or add an explicit wait.

- [ ] **Step 4: Commit any fixes**

If you made fixes during Steps 2–3, commit them with a focused message like:

```bash
git add <files>
git commit -m "Fix <specific issue> caught by smoke run"
```

If no fixes were needed, no commit. Done.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Off-time near midnight UTC**: races scheduled just after 00:00 Europe/London but scraped just before could end up dated to "today" rather than "tomorrow." Documented in the spec's open implementation questions; not handled.
- **Browser reuse across races**: today we open + close Chrome 25 times per run. A pool of one or two reused drivers would be faster but adds error-recovery complexity.
- **Re-scraping the same race over time**: out of scope — schema is "one snapshot per run, overwriting `data.json`."
