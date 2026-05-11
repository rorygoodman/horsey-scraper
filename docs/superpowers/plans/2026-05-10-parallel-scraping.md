# Parallel Race Scraping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the serial race-scrape loop in `Main.kt` with a configurable worker pool (default 3, capped at 10) that pulls races from a shared queue, so a full daily scrape drops from ~10-12 min to ~3-4 min.

**Architecture:** A new `RaceWorkerPool.kt` exposes one top-level function `scrapeRacesInParallel(races, workerCount, perWorkerDelayMs, scrapeRace, onResult)`. It builds a `LinkedBlockingQueue<Race>` from the input, starts `workerCount` threads that loop `poll()` → `scrapeRace(race)` → `onResult(...)`, joins, sorts results by `(offTime, venue)`, and returns. The `scrapeRace` lambda is a test seam — production passes `{ race -> BetfairRaceScraper(race).scrape() }`; tests pass a fake. `Main.kt` parses the worker count from the first CLI arg (default 3) and `run.sh` becomes a one-liner forwarding that arg via `--args`.

**Tech Stack:** Kotlin 1.9, JDK 17, `java.util.concurrent` (no new dependencies). Existing JUnit 5 / `kotlin("test")` test framework.

**Spec:** `docs/superpowers/specs/2026-05-10-parallel-scraping-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- `./gradlew run --quiet` runs `Main.kt`. The wrapper `./run.sh` exists so you can type fewer characters.
- `Main.kt` currently does: fetch race list → for each race in a `while` loop, open Chrome and scrape → write `data.json`.
- Each race takes ~30s and the loop sleeps 2s between races. 17-22 races a day → 10-12 min wall time. We want to parallelise that.
- All tests are JUnit 5 in `src/test/kotlin/com/horsey/scraper/`. Run with `./gradlew test`. Pre-existing test count: **40**. After this plan: **52** (+11 from this plan, +1 from a small Main test).
- The `BetfairRaceScraper(race).scrape()` call you'll be parallelising is already self-contained: each call opens its own Chrome session via `createChromeDriver()`, scrapes 5 markets, closes Chrome, and returns either `RaceOdds` (success) or `null` (no WIN — race dropped).
- Selenium calls block their thread. Threads (not coroutines) are the natural primitive.
- The data classes you'll build tests against (`Race`, `RaceOdds`, `MarketType`, etc.) live in `src/main/kotlin/com/horsey/scraper/Models.kt`.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

---

## Task 1: Build the worker pool

Pure-logic test seam. The pool function takes a `(Race) -> RaceOdds?` lambda for the scrape, so the entire pool can be unit-tested without touching a browser.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`:

```kotlin
package com.horsey.scraper

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RaceWorkerPoolTest {
    private fun fakeRace(id: String, time: String, venue: String) = Race(
        raceId = id, venue = venue, country = "GB",
        offTime = time, winMarketUrl = "https://example/$id"
    )

    private fun fakeOdds(race: Race) = RaceOdds(
        raceId = race.raceId, venue = race.venue, country = race.country,
        offTime = race.offTime, winMarketUrl = race.winMarketUrl,
        marketName = "x",
        marketScrapedAt = mapOf(MarketType.WIN to "2026-05-10T12:00:00Z"),
        runners = emptyList()
    )

    @Test
    fun `single worker scrapes all races in input off-time order`() {
        val races = listOf(
            fakeRace("1.A", "2026-05-10T13:00:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T13:30:00+01:00", "B"),
            fakeRace("1.C", "2026-05-10T14:00:00+01:00", "C"),
        )
        val results = scrapeRacesInParallel(
            races = races, workerCount = 1, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        assertEquals(listOf("1.A", "1.B", "1.C"), results.map { it.raceId })
    }

    @Test
    fun `three workers process all races exactly once`() {
        val races = (0 until 6).map {
            fakeRace("1.$it", "2026-05-10T13:0${it}:00+01:00", "V$it")
        }
        val results = scrapeRacesInParallel(
            races = races, workerCount = 3, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        assertEquals(6, results.size)
        assertEquals(races.map { it.raceId }.toSet(), results.map { it.raceId }.toSet())
    }

    @Test
    fun `result list is sorted by offTime then venue regardless of completion order`() {
        // Race C has the latest off-time; make it scrape first by being fastest.
        // Race A has the earliest off-time; make it slowest. Sort must still
        // put A before B before C in the output regardless.
        val races = listOf(
            fakeRace("1.A", "2026-05-10T13:00:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T13:30:00+01:00", "B"),
            fakeRace("1.C", "2026-05-10T14:00:00+01:00", "C"),
        )
        val results = scrapeRacesInParallel(
            races = races, workerCount = 3, perWorkerDelayMs = 0,
            scrapeRace = { race ->
                when (race.raceId) {
                    "1.A" -> Thread.sleep(150)
                    "1.B" -> Thread.sleep(80)
                    else -> { /* fast */ }
                }
                fakeOdds(race)
            },
            onResult = { _, _, _ -> }
        )
        assertEquals(listOf("1.A", "1.B", "1.C"), results.map { it.raceId })
    }

    @Test
    fun `same offTime is broken by venue alphabetically`() {
        val races = listOf(
            fakeRace("1.X", "2026-05-10T13:00:00+01:00", "Zzz"),
            fakeRace("1.Y", "2026-05-10T13:00:00+01:00", "Aaa"),
        )
        val results = scrapeRacesInParallel(
            races = races, workerCount = 2, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        assertEquals(listOf("Aaa", "Zzz"), results.map { it.venue })
    }

    @Test
    fun `null odds from scrapeRace are excluded from results but reported via onResult`() {
        val races = listOf(
            fakeRace("1.A", "2026-05-10T13:00:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T13:30:00+01:00", "B"),
        )
        val seen = mutableMapOf<String, RaceOdds?>()
        val results = scrapeRacesInParallel(
            races = races, workerCount = 1, perWorkerDelayMs = 0,
            scrapeRace = { race -> if (race.raceId == "1.A") null else fakeOdds(race) },
            onResult = { _, race, odds ->
                synchronized(seen) { seen[race.raceId] = odds }
            }
        )
        assertEquals(listOf("1.B"), results.map { it.raceId })
        assertEquals(setOf("1.A", "1.B"), seen.keys)
        assertEquals(null, seen["1.A"])
        assertEquals("1.B", seen["1.B"]?.raceId)
    }

    @Test
    fun `exception in scrapeRace is caught, logged via onResult, and does not stop the pool`() {
        val races = listOf(
            fakeRace("1.A", "2026-05-10T13:00:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T13:30:00+01:00", "B"),
            fakeRace("1.C", "2026-05-10T14:00:00+01:00", "C"),
        )
        // NB: cannot use ConcurrentHashMap here — it rejects null values, and
        // we explicitly need to record `null` for the throwing race.
        val seen = mutableMapOf<String, RaceOdds?>()
        val results = scrapeRacesInParallel(
            races = races, workerCount = 2, perWorkerDelayMs = 0,
            scrapeRace = { race ->
                if (race.raceId == "1.B") throw RuntimeException("boom")
                fakeOdds(race)
            },
            onResult = { _, race, odds ->
                synchronized(seen) { seen[race.raceId] = odds }
            }
        )
        assertEquals(setOf("1.A", "1.C"), results.map { it.raceId }.toSet())
        assertEquals(setOf("1.A", "1.B", "1.C"), seen.keys)
        assertEquals(null, seen["1.B"])
    }

    @Test
    fun `onResult is called exactly once per race`() {
        val races = (0 until 8).map {
            fakeRace("1.$it", "2026-05-10T13:0${it}:00+01:00", "V$it")
        }
        val callCounts = ConcurrentHashMap<String, AtomicInteger>()
        scrapeRacesInParallel(
            races = races, workerCount = 3, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, race, _ ->
                callCounts.computeIfAbsent(race.raceId) { AtomicInteger(0) }.incrementAndGet()
            }
        )
        assertEquals(8, callCounts.size)
        assertTrue(callCounts.values.all { it.get() == 1 },
            "expected exactly one call per race, got: ${callCounts.mapValues { it.value.get() }}")
    }

    @Test
    fun `workerCount greater than races size completes without error`() {
        val races = listOf(
            fakeRace("1.A", "2026-05-10T13:00:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T13:30:00+01:00", "B"),
        )
        val results = scrapeRacesInParallel(
            races = races, workerCount = 5, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        assertEquals(setOf("1.A", "1.B"), results.map { it.raceId }.toSet())
    }

    @Test
    fun `empty races list returns empty list`() {
        val results = scrapeRacesInParallel(
            races = emptyList(), workerCount = 3, perWorkerDelayMs = 0,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        assertEquals(emptyList(), results)
    }

    @Test
    fun `multiple workers actually run concurrently (parallel speedup)`() {
        // 4 races, each scrape sleeps 400ms. Serial = 1600ms. With 4 workers
        // running in parallel = ~400ms. Allow generous bound for JVM thread
        // start-up + scheduling: < 1000ms still proves real concurrency.
        val races = (0 until 4).map {
            fakeRace("1.$it", "2026-05-10T13:0${it}:00+01:00", "V$it")
        }
        val start = System.nanoTime()
        scrapeRacesInParallel(
            races = races, workerCount = 4, perWorkerDelayMs = 0,
            scrapeRace = { Thread.sleep(400); fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        assertTrue(elapsedMs < 1000,
            "expected parallel speedup (under 1000ms); was ${elapsedMs}ms (serial would be ~1600ms)")
    }

    @Test
    fun `per-worker delay applies between successive races on the same worker but not before the first`() {
        // N=1 worker, 3 races, perWorkerDelayMs=200. Total delay: 0 (before first)
        // + 200 (between 1 and 2) + 200 (between 2 and 3) = 400ms minimum.
        // Each scrape itself is instant. Total: ~400ms. Bound: 350..900ms.
        val races = (0 until 3).map {
            fakeRace("1.$it", "2026-05-10T13:0${it}:00+01:00", "V$it")
        }
        val start = System.nanoTime()
        scrapeRacesInParallel(
            races = races, workerCount = 1, perWorkerDelayMs = 200,
            scrapeRace = { fakeOdds(it) },
            onResult = { _, _, _ -> }
        )
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        assertTrue(elapsedMs in 350..900,
            "expected ~400ms (2x 200ms inter-race delay); was ${elapsedMs}ms")
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceWorkerPoolTest'`
Expected: FAIL with `unresolved reference: scrapeRacesInParallel`.

- [ ] **Step 3: Implement the pool**

Create `src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt`:

```kotlin
package com.horsey.scraper

import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.LinkedBlockingQueue

/**
 * Scrapes a list of races concurrently using `workerCount` threads pulling
 * from a shared queue. Returns successful (`RaceOdds`-non-null) results
 * sorted by `(offTime, venue)`.
 *
 *  - Each worker loops: `poll()` → if null, exit; else call `scrapeRace`,
 *    invoke `onResult`, sleep `perWorkerDelayMs` before the next pull.
 *    The first race on each worker has no leading delay; the last has no
 *    trailing delay.
 *  - `scrapeRace` may return null (race dropped) or throw. Both are caught
 *    inside the worker, reported via `onResult(workerId, race, null)`, and
 *    excluded from the returned list. Other races and other workers are
 *    unaffected.
 *  - `onResult` is invoked exactly once per race (success, drop, or throw).
 *    `println` is line-atomic on the JVM, so a logging `onResult` produces
 *    interleaved-but-readable output.
 *  - If `workerCount > races.size`, surplus workers exit immediately on
 *    first empty `poll()`. Harmless.
 *  - If `races` is empty, returns empty list immediately (workers still
 *    start and exit cleanly).
 */
fun scrapeRacesInParallel(
    races: List<Race>,
    workerCount: Int,
    perWorkerDelayMs: Long,
    scrapeRace: (Race) -> RaceOdds?,
    onResult: (workerId: Int, race: Race, odds: RaceOdds?) -> Unit
): List<RaceOdds> {
    val queue = LinkedBlockingQueue(races)
    val results = ConcurrentLinkedQueue<RaceOdds>()

    val threads = (0 until workerCount).map { workerId ->
        Thread({
            var first = true
            while (true) {
                val race = queue.poll() ?: break
                if (!first) Thread.sleep(perWorkerDelayMs)
                first = false

                val odds: RaceOdds? = try {
                    scrapeRace(race)
                } catch (e: Exception) {
                    System.err.println("[w$workerId] ${race.raceId} threw: ${e.javaClass.simpleName}: ${e.message}")
                    null
                }
                onResult(workerId, race, odds)
                if (odds != null) results.add(odds)
            }
        }, "horsey-worker-$workerId").apply {
            uncaughtExceptionHandler = Thread.UncaughtExceptionHandler { t, e ->
                System.err.println("Worker thread ${t.name} died: ${e.javaClass.simpleName}: ${e.message}")
            }
            start()
        }
    }
    threads.forEach { it.join() }

    return results.toList().sortedWith(compareBy({ it.offTime }, { it.venue }))
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceWorkerPoolTest'`
Expected: 11 tests PASS. (One of the timing tests — `multiple workers actually run concurrently` or `per-worker delay`— may be flaky on a heavily-loaded machine. If a timing test fails by a small margin (e.g. 1050ms when bound is 1000ms), report that as a concern rather than papering over it; we may need to widen the bound. Both bounds in the spec are intentionally generous.)

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`
Expected: 51 tests pass (40 pre-existing + 11 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt
git commit -m "Add scrapeRacesInParallel: configurable worker pool"
```

---

## Task 2: parseWorkerCount in Main.kt

A small top-level helper that parses the first CLI arg into `1..10`. Lives in `Main.kt` so it's adjacent to its only caller, but written as a top-level `fun` (not `private`) so the test in the same package can call it.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt` (add helper near the top, do NOT touch `main()` yet — that's Task 3)
- Modify: `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt` (add a small `parseWorkerCount` test class at the bottom)

- [ ] **Step 1: Write the failing tests**

Append the following to `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt` (after the closing `}` of `RaceWorkerPoolTest`):

```kotlin
class ParseWorkerCountTest {
    @Test
    fun `defaults to 3 when no args`() {
        assertEquals(3, parseWorkerCount(emptyArray()))
    }

    @Test
    fun `accepts 1`() {
        assertEquals(1, parseWorkerCount(arrayOf("1")))
    }

    @Test
    fun `accepts 10`() {
        assertEquals(10, parseWorkerCount(arrayOf("10")))
    }

    @Test
    fun `accepts 5`() {
        assertEquals(5, parseWorkerCount(arrayOf("5")))
    }

    @Test
    fun `rejects 0`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseWorkerCount(arrayOf("0"))
        }
        assertTrue("0" in (e.message ?: ""), "message was: ${e.message}")
    }

    @Test
    fun `rejects 11`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseWorkerCount(arrayOf("11"))
        }
        assertTrue("11" in (e.message ?: ""), "message was: ${e.message}")
    }

    @Test
    fun `rejects negative`() {
        assertFailsWith<IllegalArgumentException> {
            parseWorkerCount(arrayOf("-1"))
        }
    }

    @Test
    fun `rejects non-numeric`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseWorkerCount(arrayOf("abc"))
        }
        assertTrue("abc" in (e.message ?: ""), "message was: ${e.message}")
    }

    @Test
    fun `rejects empty string`() {
        assertFailsWith<IllegalArgumentException> {
            parseWorkerCount(arrayOf(""))
        }
    }
}
```

You also need to add the `assertFailsWith` import at the top of the same file. Locate the existing import block:

```kotlin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
```

Replace it with:

```kotlin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseWorkerCountTest'`
Expected: FAIL with `unresolved reference: parseWorkerCount`.

- [ ] **Step 3: Add `parseWorkerCount` to Main.kt**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Insert the following just below the `private const val OUTPUT_FILE = "data.json"` line (before the `/** Entry point: ... */` doc comment):

```kotlin
/**
 * Parses the worker-count CLI argument. First positional arg is parsed as an
 * Int in 1..10. If absent, defaults to 3. Both validation failures throw
 * `IllegalArgumentException` so the caller can catch one type and print a
 * clean error.
 */
fun parseWorkerCount(args: Array<String>): Int {
    val raw = args.firstOrNull() ?: return 3
    val n = raw.toIntOrNull()
    require(n != null) { "workers must be between 1 and 10 (got: '$raw')" }
    require(n in 1..10) { "workers must be between 1 and 10 (got: $n)" }
    return n
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseWorkerCountTest'`
Expected: 9 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`
Expected: 60 tests pass (40 pre-existing + 11 from Task 1 + 9 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt
git commit -m "Add parseWorkerCount(args): Int with 1..10 validation"
```

---

## Task 3: Wire Main.kt to use the worker pool

Replace the existing serial `while` loop with a single call to `scrapeRacesInParallel`. Worker count parsed from `args` via `parseWorkerCount`; on `IllegalArgumentException`, print a clean stderr message and exit non-zero.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Replace `main()`**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Replace the entire `fun main() { ... }` function (everything from the `/** Entry point: ... */` doc comment through the closing brace) with:

```kotlin
/**
 * Entry point: a single pass over today's UK + IE Betfair Exchange races.
 *
 *   1. Parses worker count from args[0] (default 3, range 1..10).
 *   2. Reads the race list from the horse-racing landing page.
 *   3. For each race, opens one Chrome and scrapes WIN + Top 2/3/4/5 Finish.
 *      Up to `workerCount` races run concurrently.
 *   4. Pivots into per-horse lay map and writes data.json.
 *
 * Output schema: see docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md
 * Parallelism:  see docs/superpowers/specs/2026-05-10-parallel-scraping-design.md
 */
fun main(args: Array<String>) {
    val workerCount = try {
        parseWorkerCount(args)
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    // serializeNulls is required by the spec: a `lay` map with a key whose
    // value is null means "scraped but no lay on offer." Without this,
    // Gson drops null entries and breaks key parity with marketScrapedAt.
    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()

    println("Horsey Scraper — Betfair Exchange (UK + IE) — multi-market lay")
    println("workers=$workerCount")
    println("=".repeat(80))

    val runStart = Instant.now()
    println("\n[$runStart] Fetching today's race list…")
    val races = BetfairRaceListScraper().scrape()
    println("Found ${races.size} UK/IE races today.")
    races.forEach { println("  ${it.offTime}  ${it.country}  ${it.venue}  (${it.raceId})") }

    val results = scrapeRacesInParallel(
        races = races,
        workerCount = workerCount,
        perWorkerDelayMs = PER_RACE_DELAY_MS,
        scrapeRace = { race -> BetfairRaceScraper(race).scrape() },
    ) { workerId, race, odds ->
        val tag = "[w$workerId]"
        if (odds == null) {
            println("$tag ${race.offTime} ${race.venue} (${race.raceId}) DROPPED")
        } else {
            val markets = odds.marketScrapedAt.keys.joinToString(",") { it.name }
            println("$tag ${race.offTime} ${race.venue} (${race.raceId}) → ${odds.runners.size} runners, markets=[$markets]")
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

The existing `import` block at the top of the file already covers everything except `kotlin.system.exitProcess`, which is referenced as a fully qualified name above. The `ArrayDeque` import becomes unused — Kotlin will warn but still compile. Remove the import line `import java.util.ArrayDeque` to keep the file clean.

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`. (One unused-import warning if you missed removing `ArrayDeque`; clean it up if so.)

- [ ] **Step 3: Run the full test suite**

Run: `./gradlew test`
Expected: 60 tests pass — same as Task 2 (no new tests in this task; we're verifying we haven't broken anything).

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "Wire Main to scrapeRacesInParallel; default 3 workers from args[0]"
```

---

## Task 4: Update run.sh to forward the worker-count arg

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh`**

Replace the entire contents of `run.sh` with:

```bash
#!/usr/bin/env bash
# Forward the first positional arg as the worker count (default 3).
# Examples:
#   ./run.sh        # 3 workers (default)
#   ./run.sh 1      # serial — exactly the pre-parallel behavior
#   ./run.sh 5      # 5 parallel workers (max 10)
WORKERS="${1:-3}"
exec ./gradlew run --quiet --args="$WORKERS"
```

- [ ] **Step 2: Syntax-check the script**

Run: `bash -n run.sh`
Expected: no output, exit code 0.

- [ ] **Step 3: Verify it remains executable**

Run: `ls -l run.sh`
Expected: the mode column starts with `-rwxr-xr-x` (or otherwise has the `x` bit set). If you somehow lost the executable bit, restore it with `chmod +x run.sh`.

We don't actually run `./run.sh` here — that would scrape Betfair for ~3 minutes. The smoke run in Task 5 does the live test.

- [ ] **Step 4: Commit**

```bash
git add run.sh
git commit -m "run.sh: forward \$1 as worker count via --args (default 3)"
```

---

## Task 5: End-to-end smoke run

No new code. Run the parallel scraper for real, validate the output, and confirm there's a meaningful speedup vs serial.

- [ ] **Step 1: Validate the bad-arg path**

Quick check that the error-message path works without scraping anything:

Run: `./run.sh 0 2>&1 | head -20`
Expected: contains `Error: workers must be between 1 and 10 (got: 0)` and exits non-zero.

Also try a non-numeric:

Run: `./run.sh abc 2>&1 | head -20`
Expected: contains `Error: workers must be between 1 and 10 (got: 'abc')`.

If either test produces a Java stack trace instead of a clean error message, that's a Task 3 bug — go back and fix the `try { parseWorkerCount(args) } catch` block, then re-commit before continuing.

- [ ] **Step 2: Run the parallel smoke**

```bash
./run.sh 3 2>&1 | tee /tmp/horsey-smoke-parallel.txt
```

Expected: race-list scrape, then prefixed `[w0]`, `[w1]`, `[w2]` lines interleaving as workers complete races, then `Wrote data.json (N races)`.

This should take roughly 3-5 minutes if there are ~15+ races today (vs ~10-12 min for the previous serial behavior). If today is outside UK racing hours and `Found 0 UK/IE races today` appears, that's fine — `data.json` will be a valid empty file. Skip Step 4.

DO NOT cancel mid-run. Use a long timeout (up to 30 min). If the run actually fails, don't retry blindly — read the output and diagnose.

- [ ] **Step 3: Validate the output**

```bash
./gradlew run -PmainClass=com.horsey.scraper.ValidateMainKt --args='data.json' --quiet 2>&1 | tail -5
```

Expected: `data.json: VALID (matches spec)`.

If validation reports errors, read them carefully. Most likely failure modes specific to this change:
- Duplicate race id (a race somehow got polled twice from the queue) — would show up as the same `raceId` appearing more than once. This would be a serious pool bug.
- Race ordering wrong — easy to verify with `jq -r '.races[].offTime' data.json` and confirming the list is sorted ascending.

If you find a real bug, fix it in the appropriate file (likely `RaceWorkerPool.kt`), re-run tests, re-run smoke, then commit the fix. If validation passes cleanly, no commit needed for this step.

- [ ] **Step 4: Confirm parallel speedup**

```bash
# Look at the start and end timestamps printed in the smoke output.
# The runStart line is "[<ISO instant>] Fetching today's race list…"
# The end is the "Wrote data.json" line; mtime of data.json approximates this.
grep -E "Fetching today's race list|Wrote data\.json" /tmp/horsey-smoke-parallel.txt
ls -la data.json
```

Sanity: end time minus start time should be roughly `(num_races * 30s) / workerCount + small overhead`. For 17 races and 3 workers, expect ~3-4 min; for 1 worker, ~10-12 min.

If you have time and want to confirm the speedup is real (not just appearing fast because today happens to have few races), run a serial baseline:

```bash
./run.sh 1 2>&1 | tee /tmp/horsey-smoke-serial.txt
```

Compare the elapsed times. The 3-worker run should be ≥ 2× faster than the 1-worker run. If it isn't, there's likely a hidden serialization bottleneck — chromedriver port allocation, shared browser-data directory, or similar. Investigate before declaring done.

- [ ] **Step 5: Commit any fixes**

If Step 3 or Step 4 turned up bugs you fixed, commit them with a focused message:

```bash
git add <files>
git commit -m "Fix <specific issue> caught by parallel smoke"
```

If no fixes were needed, no commit. Done.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Browser reuse across races within a worker**: today every race opens + closes Chrome (~3-5s overhead per race). Pooling browsers per worker would give another ~10-20% speedup but adds session-state management complexity.
- **chromedriver process count**: with N workers we have N chromedriver processes plus N Chrome processes. On a small machine (8GB RAM) you might want to add a hard memory check before raising the cap above 10.
- **Adaptive worker count**: we cap at 10 by hand. A future could autotune based on `Runtime.getRuntime().availableProcessors()` and remaining races.
- **Better progress reporting**: the prefixed-tag stdout works but isn't great for piping into a log aggregator. Structured (JSON-lines) logging would be a nice-to-have.
