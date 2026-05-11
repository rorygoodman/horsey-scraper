# Region CLI Arg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make region selection an explicit second positional CLI arg to `run.sh`. Default is `gb-ie` (no US). The user opts into US (or any future region) by listing it.

**Architecture:** Add a `RegionTab.regionId()` extension that derives a stable user-facing ID from each tab's name (`"GB+IE"` → `"gb-ie"`, `"US"` → `"us"`). `BetfairRaceListScraper` gains an optional `regions: Set<String>` constructor parameter; its scrape loop filters `REGION_TABS` by that set. `Main.kt` gains a `parseRegions(args)` helper that reads `args[1]`, validates against the known set, and surfaces a clean error on bad input. `run.sh` forwards `${2:-gb-ie}` as a second `--args` token. No smoke task (per spec scope decision).

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`.

**Spec:** `docs/superpowers/specs/2026-05-11-region-cli-arg-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- The scraper currently iterates `REGION_TABS = [GB+IE, US]` in `BetfairRaceListScraper.kt`. Each entry is a `RegionTab(name, flagsRequired, countryOverride)`. The `scrape()` loop activates each tab in turn and accumulates races.
- US scraping was added recently and is currently always-on. The user wants it off by default, on by explicit opt-in.
- `Main.kt` already has a `parseWorkerCount(args: Array<String>): Int` helper that parses `args[0]`. We add a parallel `parseRegions(args)` that parses `args[1]`. They don't conflict — different indices.
- Existing tests in `BetfairRaceListScraperTest.kt`, `RaceWorkerPoolTest.kt`, etc. construct `BetfairRaceListScraper()` with the default constructor; the new `regions` parameter has a default value so those calls keep compiling without changes.
- Pre-existing test count: 66 (run `./gradlew test` to confirm baseline). After this plan: 74 (+8 from `ParseRegionsTest`).
- All changes here are pure-logic + CLI plumbing. No browser interaction.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

---

## Task 1: `regionId()` extension + `regions` filter in `BetfairRaceListScraper`

Add the extension function that gives each `RegionTab` a stable user-facing ID. Add the optional `regions` constructor parameter and use it to filter the scrape loop. Defaulted parameter means existing tests stay green with no changes.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt`

- [ ] **Step 1: Add `regionId()` extension just below the `REGION_TABS` declaration**

Open `src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt`. Find the `REGION_TABS` declaration block (right above `class BetfairRaceListScraper`). Immediately after the closing `)` of `REGION_TABS`, before the `class` keyword, insert:

```kotlin
/**
 * Stable user-facing ID for a region. Lower-cased, with `+` replaced by `-`
 * so it's easy to type as a CLI arg. Used by both the CLI parser
 * ([com.horsey.scraper.parseRegions]) and the constructor's `regions`
 * filter to identify tabs.
 */
internal fun RegionTab.regionId(): String = name.lowercase().replace("+", "-")
```

- [ ] **Step 2: Add `regions` constructor parameter to `BetfairRaceListScraper`**

In the same file, find the class header:

```kotlin
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7"
) {
```

Replace it with:

```kotlin
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7",
    private val regions: Set<String> = REGION_TABS.map { it.regionId() }.toSet(),
) {
```

The default — "all configured regions" — preserves today's behavior for any caller that doesn't specify `regions`. That's why no existing test needs updating.

- [ ] **Step 3: Filter the scrape loop by `regions`**

In the same file, find the `for (region in REGION_TABS) { ... }` line inside `scrape()`. Replace just that `for` line with:

```kotlin
            for (region in REGION_TABS.filter { it.regionId() in regions }) {
```

Nothing else changes inside the loop body.

- [ ] **Step 4: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: Run the full test suite**

Run: `./gradlew test`
Expected: 66 tests pass (same count as before this task — no new tests).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt
git commit -m "BetfairRaceListScraper: filter REGION_TABS by an optional regions set"
```

---

## Task 2: `parseRegions` in `Main.kt` + 8 validation tests

Strict TDD. The helper reads `args[1]`, splits on commas, lowercases, validates against the known region IDs derived from `REGION_TABS`. Throws `IllegalArgumentException` on bad input so `main` can catch and exit cleanly.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`

- [ ] **Step 1: Write the failing tests**

Open `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`. Append a new test class at the bottom of the file (after the closing `}` of `ParseWorkerCountTest`):

```kotlin
class ParseRegionsTest {
    @Test
    fun `defaults to gb-ie when no second arg`() {
        assertEquals(setOf("gb-ie"), parseRegions(emptyArray()))
        assertEquals(setOf("gb-ie"), parseRegions(arrayOf("3")))
    }

    @Test
    fun `accepts us only`() {
        assertEquals(setOf("us"), parseRegions(arrayOf("3", "us")))
    }

    @Test
    fun `accepts comma-separated list`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", "gb-ie,us")))
    }

    @Test
    fun `accepts uppercase`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", "GB-IE,US")))
    }

    @Test
    fun `trims whitespace around ids`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", " gb-ie , us ")))
    }

    @Test
    fun `rejects unknown region with helpful message listing valid ids`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseRegions(arrayOf("3", "fr"))
        }
        assertTrue("fr" in (e.message ?: ""), "message must mention the bad id: ${e.message}")
        assertTrue("gb-ie" in (e.message ?: "") && "us" in (e.message ?: ""),
            "message must list valid ids: ${e.message}")
    }

    @Test
    fun `rejects empty string`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("3", "")) }
    }

    @Test
    fun `rejects single comma (no real ids)`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("3", ",")) }
    }
}
```

(The `assertFailsWith` and `assertTrue` imports were added to the file in PT2 of an earlier plan; verify they're present at the top of the file and add them if not.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseRegionsTest'`
Expected: FAIL with `unresolved reference: parseRegions`.

- [ ] **Step 3: Add `parseRegions` to `Main.kt`**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Find the existing `parseWorkerCount` function (top of the file, just under `OUTPUT_FILE`). Immediately after its closing `}`, insert:

```kotlin
/**
 * Parses the regions CLI argument. Second positional arg is a
 * comma-separated set of region IDs (case-insensitive, whitespace-tolerant).
 * If absent, defaults to `setOf("gb-ie")`.
 *
 * Region IDs are derived from `REGION_TABS` via [RegionTab.regionId].
 * Unknown IDs cause an `IllegalArgumentException` whose message lists the
 * bad id(s) alongside the valid set, so the caller can surface a clean
 * error message. An empty arg (or one that parses to no ids) also throws.
 */
fun parseRegions(args: Array<String>): Set<String> {
    val raw = args.getOrNull(1) ?: return setOf("gb-ie")
    val ids = raw.split(",").map { it.trim().lowercase() }
        .filter { it.isNotEmpty() }
        .toSet()
    val known = REGION_TABS.map { it.regionId() }.toSet()
    val unknown = ids - known
    require(unknown.isEmpty()) {
        "unknown region(s) ${unknown.joinToString(",")}; valid: ${known.sorted().joinToString(",")}"
    }
    require(ids.isNotEmpty()) {
        "regions must be non-empty; valid: ${known.sorted().joinToString(",")}"
    }
    return ids
}
```

`REGION_TABS` and `regionId()` are declared in `BetfairRaceListScraper.kt` in the same `com.horsey.scraper` package, so no extra import is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseRegionsTest'`
Expected: 8 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`
Expected: 74 tests pass (66 from after Task 1 + 8 new).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt
git commit -m "Add parseRegions(args): Set<String> with default gb-ie and validation"
```

---

## Task 3: Wire `Main.main` to parse regions and pass them to the scraper

Hook `parseRegions` into `main` next to the existing `parseWorkerCount` call. Pass the parsed set into `BetfairRaceListScraper`. Print a `regions=…` line in the startup log.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Replace the relevant block in `main`**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Find this block at the top of `fun main(args: Array<String>)`:

```kotlin
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
```

Replace it with:

```kotlin
    val workerCount = try {
        parseWorkerCount(args)
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }
    val regions = try {
        parseRegions(args)
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    // serializeNulls is required by the spec: a `lay` map with a key whose
    // value is null means "scraped but no lay on offer." Without this,
    // Gson drops null entries and breaks key parity with marketScrapedAt.
    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()

    println("Horsey Scraper — Betfair Exchange — multi-market lay")
    println("workers=$workerCount")
    println("regions=${regions.sorted().joinToString(",")}")
    println("=".repeat(80))
```

(The "UK + IE" string is removed from the banner since regions are now configurable.)

Then find the line:

```kotlin
    val races = BetfairRaceListScraper().scrape()
```

Replace with:

```kotlin
    val races = BetfairRaceListScraper(regions = regions).scrape()
```

- [ ] **Step 2: Verify it compiles**

Run: `./gradlew compileKotlin`
Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Run the full test suite**

Run: `./gradlew test`
Expected: 74 tests pass (no new tests in this task; verifying nothing broke).

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "Wire Main: parse regions, log them, pass to BetfairRaceListScraper"
```

---

## Task 4: Update `run.sh` to forward the regions arg

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh`**

Replace the entire contents of `run.sh` with:

```bash
#!/usr/bin/env bash
# Forward two positional args to the scraper:
#   $1 = worker count (default 3, range 1..10)
#   $2 = regions      (default gb-ie; comma-separated; valid: gb-ie,us)
# Examples:
#   ./run.sh                # 3 workers, GB+IE only
#   ./run.sh 1              # 1 worker,  GB+IE only
#   ./run.sh 3 us           # 3 workers, US only
#   ./run.sh 3 gb-ie,us     # 3 workers, both
WORKERS="${1:-3}"
REGIONS="${2:-gb-ie}"
exec ./gradlew run --quiet --args="$WORKERS $REGIONS"
```

- [ ] **Step 2: Syntax-check the script**

Run: `bash -n run.sh`
Expected: no output, exit code 0.

- [ ] **Step 3: Verify it remains executable**

Run: `ls -l run.sh`
Expected: the mode column starts with `-rwxr-xr-x` (or otherwise has the `x` bit set). If you somehow lost the executable bit, restore it with `chmod +x run.sh`.

- [ ] **Step 4: Verify the bad-region exit path works (no actual scrape)**

Run: `./run.sh 3 fr 2>&1 | head -5`
Expected: contains `Error: unknown region(s) fr; valid: gb-ie,us`. The gradle "BUILD FAILED" noise after the error is cosmetic, ignore it. We don't run a positive scrape here — that's the user's call.

- [ ] **Step 5: Commit**

```bash
git add run.sh
git commit -m "run.sh: forward \$2 as regions (default gb-ie)"
```

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Per-country control within the GB+IE tab.** You can't ask for "GB races only"; the Betfair tab combines GB and IE. Out of scope by user decision.
- **Smoke run.** Per the user, no live smoke needed for this change. The previous US-racing smoke already verified the multi-tab path; this change is pure filtering on top.
- **Named flag form (`--regions=…`).** Skipped in favor of the simpler positional arg.
- **Env-var fallback (`HORSEY_REGIONS=…`).** YAGNI.
- **The cosmetic "BUILD FAILED" noise** that gradle prints after our clean error message. Same issue we noted in the parallel-scraping plan; could be cleaned up by parsing args in bash before invoking gradle.
