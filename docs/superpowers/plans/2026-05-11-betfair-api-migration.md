# Betfair API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every Selenium/Chrome scraping path with calls to the Betfair Exchange REST API. Output `data.json` keeps its schema and passes the existing `SchemaValidator` unchanged.

**Architecture:** Hand-rolled HTTP via `java.net.http.HttpClient` + Gson. New `BetfairClient` wraps three endpoints (login, `listMarketCatalogue`, `listMarketBook`). Two thin fetchers (`RaceListFetcher`, `RaceOddsFetcher`) replace the old scrapers. Pure data transforms (`MarketClassifier`, race-from-catalogue, lay-from-marketBook, credentials parser) are unit-tested. Selenium, the worker pool, and all debug mains are deleted.

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`, Gson, `java.net.http.HttpClient` from the JDK.

**Spec:** `docs/superpowers/specs/2026-05-11-betfair-api-migration-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- This repo is a one-shot CLI that writes a `data.json` for today's UK + Irish horse racing (and optionally US). The output schema is strict — see `src/main/kotlin/com/horsey/scraper/Models.kt` and `SchemaValidator.kt`. Don't change those: this plan preserves the schema byte-for-byte.
- The existing scraper drives Chrome via Selenium. We're tearing that out. The Betfair Exchange API gives us the same data via three REST endpoints, faster and more reliably.
- The pure data-transform tests (`RunnerPivotTest`, `OffTimeBuilderTest`, `SchemaValidatorTest`, `RaceIdParserTest`, `MarketTypeTest`, `ModelsJsonTest`, `SanityTest`) survive unchanged — they were always the safety net for the output contract, not the scrape mechanism.
- Auth uses **interactive login** (POST to `identitysso.betfair.com/api/login` with username/password, returns an `ssoid` session token). The account must have 2FA disabled — `LOGIN_RESTRICTED` is the symptom if it isn't.
- Credentials live at `~/.horsey-scraper/credentials.json`. Tests use temp files; live runs need a real file.
- All HTTP is hand-rolled. No new Maven dependencies — `java.net.http.HttpClient` ships with JDK 11+ and we already have Gson.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

### About credentials in tests

No test in this plan makes a live API call. The only place credentials matter is the `Credentials` parser/loader, which is tested with temp files containing canned JSON. Never commit a real `credentials.json`. The plan adds `credentials.json` and `*.env` to `.gitignore` as defence-in-depth even though the real file lives outside the repo.

### Order of operations

Phase A (Tasks 1–7): Add new pure code alongside the old scraper. Everything still compiles; existing tests stay green.

Phase B (Tasks 8–10): Switch `Main.kt` to the new path. Old scraper code becomes unreachable but still compiles.

Phase C (Tasks 11–15): Delete the old scraper, drop Selenium from `build.gradle.kts`, update `run.sh`, add `.gitignore` and `README.md`, smoke validation.

---

## Task 0: Pre-flight check

Establish a clean baseline so the diff at the end is obvious.

- [ ] **Step 1: Confirm the working tree is clean**

Run: `git status`

Expected: `nothing to commit, working tree clean`. If anything is modified or untracked, stop and surface it to the user — those are unrelated WIP changes that need to be resolved (committed, stashed, or discarded) before this plan starts.

- [ ] **Step 2: Capture the baseline test count**

Run: `./gradlew test 2>&1 | tail -20`

Expected: `BUILD SUCCESSFUL`. Note the test count reported (you can also grep with `./gradlew test 2>&1 | grep -E 'Tests run|tests completed'`). Record it; we'll reference it at each new-test task.

For the rest of this plan we'll call this baseline **N₀**. (At the time of writing it should be 74; verify on your tree.)

- [ ] **Step 3: Confirm the spec is at HEAD**

Run: `git log --oneline -1 docs/superpowers/specs/2026-05-11-betfair-api-migration-design.md`

Expected: one commit, recent, titled along the lines of "Add design spec: replace scraping with Betfair Exchange API". If the file is missing, stop — you're on the wrong branch.

---

## Task 1: `Regions.kt` — country mapping

Add the tiny region → country-codes lookup that replaces the old `Venues.kt` and the `REGION_TABS` list. Pure data, TDD.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/Regions.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RegionsTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RegionsTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RegionsTest {
    @Test
    fun `gb-ie maps to GB and IE`() {
        assertEquals(setOf("GB", "IE"), Regions.countriesFor("gb-ie"))
    }

    @Test
    fun `us maps to US`() {
        assertEquals(setOf("US"), Regions.countriesFor("us"))
    }

    @Test
    fun `unknown region returns null`() {
        assertNull(Regions.countriesFor("fr"))
    }

    @Test
    fun `all returns both regions`() {
        assertEquals(setOf("gb-ie", "us"), Regions.ALL)
    }

    @Test
    fun `countriesForAll unions all selected regions`() {
        assertEquals(setOf("GB", "IE", "US"), Regions.countriesForAll(setOf("gb-ie", "us")))
        assertEquals(setOf("GB", "IE"), Regions.countriesForAll(setOf("gb-ie")))
        assertEquals(setOf("US"), Regions.countriesForAll(setOf("us")))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RegionsTest'`

Expected: FAIL with `unresolved reference: Regions`.

- [ ] **Step 3: Implement `Regions.kt`**

Create `src/main/kotlin/com/horsey/scraper/Regions.kt`:

```kotlin
package com.horsey.scraper

/**
 * User-facing region IDs to Betfair country codes.
 *
 * Region IDs are stable and lower-case so they round-trip as CLI args
 * (`gb-ie`, `us`). Country codes follow the Betfair API's `event.countryCode`
 * (`GB`, `IE`, `US`).
 */
object Regions {
    private val table: Map<String, Set<String>> = linkedMapOf(
        "gb-ie" to setOf("GB", "IE"),
        "us"    to setOf("US"),
    )

    val ALL: Set<String> = table.keys

    fun countriesFor(regionId: String): Set<String>? = table[regionId]

    /**
     * Union of country codes for every region in `regionIds`. Assumes ids are
     * valid (caller validates first via [countriesFor]).
     */
    fun countriesForAll(regionIds: Set<String>): Set<String> =
        regionIds.flatMap { table.getValue(it) }.toSet()
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RegionsTest'`

Expected: 5 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: N₀ + 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Regions.kt src/test/kotlin/com/horsey/scraper/RegionsTest.kt
git commit -m "Add Regions.kt: user-facing region ids to Betfair country codes"
```

---

## Task 2: Move `parseRegions` tests, switch impl to `Regions`

`parseRegions` currently lives in `Main.kt` and validates against `REGION_TABS` in `BetfairRaceListScraper.kt`. Both go away in later tasks. Move the parser's validation source to `Regions.ALL`, and lift its tests out of `RaceWorkerPoolTest.kt` (which we'll delete in Task 11) into a standalone test file.

**Files:**
- Create: `src/test/kotlin/com/horsey/scraper/ParseRegionsTest.kt`
- Modify: `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Create the new test file with the migrated tests**

Create `src/test/kotlin/com/horsey/scraper/ParseRegionsTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ParseRegionsTest {
    @Test
    fun `defaults to gb-ie when no arg`() {
        assertEquals(setOf("gb-ie"), parseRegions(emptyArray()))
    }

    @Test
    fun `accepts us only`() {
        assertEquals(setOf("us"), parseRegions(arrayOf("us")))
    }

    @Test
    fun `accepts comma-separated list`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("gb-ie,us")))
    }

    @Test
    fun `accepts uppercase`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("GB-IE,US")))
    }

    @Test
    fun `trims whitespace around ids`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf(" gb-ie , us ")))
    }

    @Test
    fun `rejects unknown region with helpful message listing valid ids`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseRegions(arrayOf("fr"))
        }
        assertTrue("fr" in (e.message ?: ""), "message must mention the bad id: ${e.message}")
        assertTrue("gb-ie" in (e.message ?: "") && "us" in (e.message ?: ""),
            "message must list valid ids: ${e.message}")
    }

    @Test
    fun `rejects empty string`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("")) }
    }

    @Test
    fun `rejects single comma (no real ids)`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf(",")) }
    }
}
```

Note the arg index has changed: `args[0]` is now `regions` (the `workers` arg goes away in Task 10).

- [ ] **Step 2: Remove the old `ParseRegionsTest` class from `RaceWorkerPoolTest.kt`**

Open `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`. Find the `class ParseRegionsTest { … }` block (it follows `ParseWorkerCountTest`) and delete the entire class including its closing `}`. Leave `ParseWorkerCountTest` and the rest of the file intact — we delete that file in Task 11.

- [ ] **Step 3: Run the new test file to verify it fails (different reasons than before)**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseRegionsTest'`

Expected: FAIL. At least one of the tests will fail because the existing `parseRegions` still reads `args[1]`, not `args[0]`. (The "rejects unknown" + "valid set" tests will pass because the message format already matches.)

- [ ] **Step 4: Rewrite `parseRegions` in `Main.kt`**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Find the existing `parseRegions` function (the one with the KDoc starting "Parses the regions CLI argument. Second positional arg…"). Replace the whole function (KDoc included) with:

```kotlin
/**
 * Parses the regions CLI argument. First positional arg is a
 * comma-separated set of region IDs (case-insensitive, whitespace-tolerant).
 * If absent, defaults to `setOf("gb-ie")`.
 *
 * Region IDs come from [Regions.ALL]. Unknown IDs throw
 * `IllegalArgumentException` whose message lists the bad id(s) alongside
 * the valid set, so the caller can surface a clean error. An empty arg
 * (or one that parses to no ids) also throws.
 */
fun parseRegions(args: Array<String>): Set<String> {
    val raw = args.getOrNull(0) ?: return setOf("gb-ie")
    val ids = raw.split(",").map { it.trim().lowercase() }
        .filter { it.isNotEmpty() }
        .toSet()
    val known = Regions.ALL
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

- [ ] **Step 5: Run the new test file to verify it passes**

Run: `./gradlew test --tests 'com.horsey.scraper.ParseRegionsTest'`

Expected: 8 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: N₀ + 5 tests pass (Task 1's 5 new + 8 ParseRegionsTest, minus 8 ParseRegionsTest that we removed from RaceWorkerPoolTest — net +5 from Task 1). If the count is different, investigate before continuing.

- [ ] **Step 7: Commit**

```bash
git add src/test/kotlin/com/horsey/scraper/ParseRegionsTest.kt src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "parseRegions: validate against Regions.ALL, move tests to own file"
```

---

## Task 3: `Credentials.kt` — parser, loader, path resolver

Strict TDD. Pure parser first, then a thin IO wrapper and the default-path resolver.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/Credentials.kt`
- Create: `src/test/kotlin/com/horsey/scraper/CredentialsTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/CredentialsTest.kt`:

```kotlin
package com.horsey.scraper

import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CredentialsTest {
    @Test
    fun `parses happy path`() {
        val c = parseCredentials("""
            { "username": "alice", "password": "hunter2", "appKey": "key-123" }
        """.trimIndent())
        assertEquals(Credentials("alice", "hunter2", "key-123"), c)
    }

    @Test
    fun `ignores extra fields`() {
        val c = parseCredentials("""
            { "username": "a", "password": "b", "appKey": "k", "note": "ignore me" }
        """.trimIndent())
        assertEquals(Credentials("a", "b", "k"), c)
    }

    @Test
    fun `rejects missing username`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "password": "b", "appKey": "k" }""")
        }
        assertTrue("username" in (e.message ?: ""))
    }

    @Test
    fun `rejects missing password`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "username": "a", "appKey": "k" }""")
        }
        assertTrue("password" in (e.message ?: ""))
    }

    @Test
    fun `rejects missing appKey`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{ "username": "a", "password": "b" }""")
        }
        assertTrue("appKey" in (e.message ?: ""))
    }

    @Test
    fun `lists every missing field in one message`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseCredentials("""{}""")
        }
        val m = e.message ?: ""
        assertTrue("username" in m && "password" in m && "appKey" in m,
            "message must list all missing fields: $m")
    }

    @Test
    fun `rejects malformed JSON`() {
        assertFailsWith<IllegalArgumentException> { parseCredentials("not json") }
    }

    @Test
    fun `loadCredentials reads file`() {
        val dir = Files.createTempDirectory("horsey-cred-test")
        val file = dir.resolve("credentials.json")
        Files.writeString(file, """{ "username": "a", "password": "b", "appKey": "k" }""")
        assertEquals(Credentials("a", "b", "k"), loadCredentials(file))
    }

    @Test
    fun `loadCredentials throws with path on missing file`() {
        val missing = Files.createTempDirectory("horsey-cred-test").resolve("nope.json")
        val e = assertFailsWith<IllegalArgumentException> { loadCredentials(missing) }
        assertTrue(missing.toString() in (e.message ?: ""),
            "message must name the missing file: ${e.message}")
    }

    @Test
    fun `loadCredentials warns on non-0600 mode but still loads`() {
        // POSIX only — skipped on Windows but our CI/dev is mac/linux.
        val dir = Files.createTempDirectory("horsey-cred-test")
        val file = dir.resolve("credentials.json")
        Files.writeString(file, """{ "username": "a", "password": "b", "appKey": "k" }""")
        Files.setPosixFilePermissions(file, PosixFilePermissions.fromString("rw-r--r--"))
        // Should not throw — warning is to stderr.
        val c = loadCredentials(file)
        assertEquals("a", c.username)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.CredentialsTest'`

Expected: FAIL with `unresolved reference: Credentials` / `parseCredentials` / `loadCredentials`.

- [ ] **Step 3: Implement `Credentials.kt`**

Create `src/main/kotlin/com/horsey/scraper/Credentials.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.attribute.PosixFileAttributeView

data class Credentials(
    val username: String,
    val password: String,
    val appKey: String,
)

/**
 * Pure parser. Accepts a JSON object with string fields `username`,
 * `password`, `appKey`. Extra fields are ignored. Missing fields throw
 * `IllegalArgumentException` listing every offender in one message.
 */
fun parseCredentials(json: String): Credentials {
    val root: JsonObject = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        throw IllegalArgumentException("credentials JSON is not a valid object: ${e.message}")
    }
    val missing = mutableListOf<String>()
    fun stringOrMiss(key: String): String? {
        val el = root.get(key)
        if (el == null || !el.isJsonPrimitive || !el.asJsonPrimitive.isString) {
            missing += key; return null
        }
        return el.asString
    }
    val username = stringOrMiss("username")
    val password = stringOrMiss("password")
    val appKey   = stringOrMiss("appKey")
    require(missing.isEmpty()) {
        "credentials JSON missing or non-string fields: ${missing.joinToString(",")}"
    }
    return Credentials(username!!, password!!, appKey!!)
}

/** Default path: `~/.horsey-scraper/credentials.json`. */
fun defaultCredentialsPath(): Path =
    Paths.get(System.getProperty("user.home"), ".horsey-scraper", "credentials.json")

/**
 * Reads and parses the credentials file at [path]. Errors with the path
 * embedded for easy debugging. If the file mode is wider than `0600` on a
 * POSIX filesystem, prints a single warning to stderr and continues.
 */
fun loadCredentials(path: Path): Credentials {
    if (!Files.exists(path)) {
        throw IllegalArgumentException("credentials file not found: $path")
    }
    warnIfWorldReadable(path)
    val json = try {
        Files.readString(path)
    } catch (e: Exception) {
        throw IllegalArgumentException("failed to read $path: ${e.message}")
    }
    return parseCredentials(json)
}

private fun warnIfWorldReadable(path: Path) {
    val view = Files.getFileAttributeView(
        path, PosixFileAttributeView::class.java, LinkOption.NOFOLLOW_LINKS
    ) ?: return
    val perms = view.readAttributes().permissions()
    val tooOpen = perms.any { it.name.startsWith("GROUP_") || it.name.startsWith("OTHERS_") }
    if (tooOpen) {
        System.err.println("Warning: $path is readable by group/others; recommend `chmod 600`.")
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.CredentialsTest'`

Expected: 10 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 10. (Tasks 1+2 added 5 net new; this adds 10.)

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Credentials.kt src/test/kotlin/com/horsey/scraper/CredentialsTest.kt
git commit -m "Add Credentials: parser, loader, default path, 0600 warning"
```

---

## Task 4: `MarketClassifier.kt` — classify Top-N markets

Pure function `classifyTopN(name, numberOfWinners): MarketType?`. Same filter as the old `RelatedMarketsFinder` applied via DOM text.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/MarketClassifier.kt`
- Create: `src/test/kotlin/com/horsey/scraper/MarketClassifierTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/MarketClassifierTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MarketClassifierTest {
    @Test
    fun `Top 2 Finish with numberOfWinners 2 classifies as TOP_2`() {
        assertEquals(MarketType.TOP_2, classifyTopN("Top 2 Finish", 2))
    }

    @Test
    fun `Top 3 4 5 Finish classify correctly`() {
        assertEquals(MarketType.TOP_3, classifyTopN("Top 3 Finish", 3))
        assertEquals(MarketType.TOP_4, classifyTopN("Top 4 Finish", 4))
        assertEquals(MarketType.TOP_5, classifyTopN("Top 5 Finish", 5))
    }

    @Test
    fun `case insensitive on name`() {
        assertEquals(MarketType.TOP_3, classifyTopN("top 3 finish", 3))
        assertEquals(MarketType.TOP_4, classifyTopN("TOP 4 FINISH", 4))
    }

    @Test
    fun `name N and numberOfWinners must match`() {
        assertNull(classifyTopN("Top 3 Finish", 2))
        assertNull(classifyTopN("Top 4 Finish", 5))
    }

    @Test
    fun `To Be Placed market is rejected`() {
        assertNull(classifyTopN("To Be Placed", 2))
        assertNull(classifyTopN("To Be Placed", 3))
    }

    @Test
    fun `arbitrary other names are rejected`() {
        assertNull(classifyTopN("Each Way", 2))
        assertNull(classifyTopN("Without Favourite", 1))
        assertNull(classifyTopN("Top 6 Finish", 6))
        assertNull(classifyTopN("Top 1 Finish", 1))
    }

    @Test
    fun `whitespace-padded name is accepted`() {
        assertEquals(MarketType.TOP_2, classifyTopN("  Top 2 Finish  ", 2))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.MarketClassifierTest'`

Expected: FAIL with `unresolved reference: classifyTopN`.

- [ ] **Step 3: Implement `MarketClassifier.kt`**

Create `src/main/kotlin/com/horsey/scraper/MarketClassifier.kt`:

```kotlin
package com.horsey.scraper

private val TOP_N_REGEX = Regex("""^top ([2-5]) finish$""", RegexOption.IGNORE_CASE)

/**
 * Classifies a PLACE market by name + winners count into one of our
 * `TOP_2..TOP_5` `MarketType`s. Returns null for anything that isn't an
 * explicit Top-N Finish market (e.g. the regular "To Be Placed" market,
 * an Each Way variant, or a Top-N where the name and `numberOfWinners`
 * disagree). Mirrors the old `RelatedMarketsFinder` text filter.
 */
fun classifyTopN(name: String, numberOfWinners: Int): MarketType? {
    val match = TOP_N_REGEX.matchEntire(name.trim()) ?: return null
    val n = match.groupValues[1].toInt()
    if (n != numberOfWinners) return null
    return when (n) {
        2 -> MarketType.TOP_2
        3 -> MarketType.TOP_3
        4 -> MarketType.TOP_4
        5 -> MarketType.TOP_5
        else -> null
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.MarketClassifierTest'`

Expected: 7 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 7.

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/MarketClassifier.kt src/test/kotlin/com/horsey/scraper/MarketClassifierTest.kt
git commit -m "Add classifyTopN: Top N Finish name + numberOfWinners classification"
```

---

## Task 5: Pure API response parsers — `BetfairResponses.kt`

Three pure functions for turning JSON responses into our domain types. TDD throughout. No HTTP.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/BetfairResponses.kt`
- Create: `src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BetfairResponsesTest {
    // --- parseSsoid ---
    @Test
    fun `parseSsoid extracts token on SUCCESS`() {
        val json = """{ "token": "abc123", "status": "SUCCESS", "error": "" }"""
        assertEquals("abc123", parseSsoid(json))
    }

    @Test
    fun `parseSsoid throws on non-SUCCESS with status in message`() {
        val json = """{ "token": "", "status": "LOGIN_RESTRICTED", "error": "" }"""
        val e = assertFailsWith<IllegalStateException> { parseSsoid(json) }
        assertTrue("LOGIN_RESTRICTED" in (e.message ?: ""), e.message)
    }

    @Test
    fun `parseSsoid mentions 2FA hint on LOGIN_RESTRICTED`() {
        val json = """{ "token": "", "status": "LOGIN_RESTRICTED", "error": "" }"""
        val e = assertFailsWith<IllegalStateException> { parseSsoid(json) }
        assertTrue("2FA" in (e.message ?: ""), "expected 2FA hint: ${e.message}")
    }

    @Test
    fun `parseSsoid throws on malformed JSON`() {
        assertFailsWith<IllegalStateException> { parseSsoid("not json") }
    }

    // --- raceFromCatalogue ---
    @Test
    fun `raceFromCatalogue builds Race from a WIN market entry`() {
        val json = """
        {
          "marketId": "1.249508314",
          "marketName": "5f Hcap",
          "marketStartTime": "2026-05-09T12:30:00.000Z",
          "description": { "marketType": "WIN", "numberOfWinners": 1 },
          "event": { "id": "32189123", "countryCode": "GB", "venue": "Lingfield" }
        }
        """.trimIndent()
        val race = raceFromCatalogue(json)
        assertEquals("1.249508314", race!!.raceId)
        assertEquals("Lingfield", race.venue)
        assertEquals("GB", race.country)
        // 12:30 UTC in May is 13:30 BST (+01:00) Europe/London.
        assertEquals("2026-05-09T13:30:00+01:00", race.offTime)
        assertEquals(
            "https://www.betfair.com/exchange/plus/horse-racing/market/1.249508314",
            race.winMarketUrl
        )
    }

    @Test
    fun `raceFromCatalogue handles winter UTC offset`() {
        val json = """
        {
          "marketId": "1.1",
          "marketName": "Mdn",
          "marketStartTime": "2026-01-15T14:30:00.000Z",
          "description": { "marketType": "WIN", "numberOfWinners": 1 },
          "event": { "id": "1", "countryCode": "GB", "venue": "Lingfield" }
        }
        """.trimIndent()
        val race = raceFromCatalogue(json)
        assertEquals("2026-01-15T14:30:00Z", race!!.offTime)
    }

    @Test
    fun `raceFromCatalogue returns null when required fields missing`() {
        val noVenue = """
        {
          "marketId": "1.1",
          "marketStartTime": "2026-05-09T12:30:00.000Z",
          "description": { "marketType": "WIN" },
          "event": { "id": "1", "countryCode": "GB" }
        }
        """.trimIndent()
        assertNull(raceFromCatalogue(noVenue))
    }

    // --- layPricesFromBook ---
    @Test
    fun `layPricesFromBook returns selectionId to best lay`() {
        val json = """
        {
          "marketId": "1.249508314",
          "status": "OPEN",
          "runners": [
            { "selectionId": 111, "status": "ACTIVE",
              "ex": { "availableToLay": [ { "price": 4.8, "size": 12.5 }, { "price": 5.0, "size": 25.0 } ] } },
            { "selectionId": 222, "status": "ACTIVE",
              "ex": { "availableToLay": [] } },
            { "selectionId": 333, "status": "ACTIVE",
              "ex": { "availableToLay": [ { "price": 22.0, "size": 4.0 } ] } }
          ]
        }
        """.trimIndent()
        val result = layPricesFromBook(json)
        assertEquals(MarketBookStatus.OPEN, result.status)
        assertEquals(mapOf(111L to 4.8, 222L to null, 333L to 22.0), result.layBySelectionId)
    }

    @Test
    fun `layPricesFromBook reports SUSPENDED`() {
        val json = """
        { "marketId": "1.1", "status": "SUSPENDED", "runners": [] }
        """.trimIndent()
        val result = layPricesFromBook(json)
        assertEquals(MarketBookStatus.OTHER, result.status)
        assertTrue(result.layBySelectionId.isEmpty())
    }

    @Test
    fun `layPricesFromBook treats unknown status as OTHER`() {
        val json = """{ "marketId": "1.1", "status": "WEIRD", "runners": [] }"""
        assertEquals(MarketBookStatus.OTHER, layPricesFromBook(json).status)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairResponsesTest'`

Expected: FAIL with unresolved references for `parseSsoid`, `raceFromCatalogue`, `layPricesFromBook`, `MarketBookStatus`.

- [ ] **Step 3: Implement `BetfairResponses.kt`**

Create `src/main/kotlin/com/horsey/scraper/BetfairResponses.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val LONDON = ZoneId.of("Europe/London")

enum class MarketBookStatus { OPEN, OTHER }

data class MarketBookSnapshot(
    val status: MarketBookStatus,
    /** selectionId → best lay price; value is `null` when `availableToLay` is empty. */
    val layBySelectionId: Map<Long, Double?>,
)

/**
 * Parses the response body of `POST /api/login` and returns the ssoid token.
 * Throws `IllegalStateException` on any non-`SUCCESS` status or malformed
 * JSON. The error message includes the status string and, for the very
 * common `LOGIN_RESTRICTED` case, a hint about 2FA being incompatible with
 * interactive login.
 */
fun parseSsoid(json: String): String {
    val root: JsonObject = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        throw IllegalStateException("login response is not a valid JSON object: ${e.message}")
    }
    val status = root.get("status")?.asString ?: "UNKNOWN"
    if (status != "SUCCESS") {
        val hint = if (status == "LOGIN_RESTRICTED")
            " — this likely means 2FA is enabled on the account. 2FA must be disabled for interactive login, or switch to cert-based login."
            else ""
        throw IllegalStateException("login failed with status=$status$hint")
    }
    return root.get("token")?.asString
        ?: throw IllegalStateException("login response has SUCCESS status but no token")
}

/**
 * Builds a [Race] from a single `MarketCatalogue` JSON object. Returns null
 * if any required field is missing or unparseable.
 */
fun raceFromCatalogue(json: String): Race? {
    val root = try {
        JsonParser.parseString(json).asJsonObject
    } catch (e: Exception) {
        return null
    }
    return raceFromCatalogue(root)
}

internal fun raceFromCatalogue(root: JsonObject): Race? {
    val marketId = root.get("marketId")?.asString ?: return null
    val startUtc = root.get("marketStartTime")?.asString ?: return null
    val event = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject ?: return null
    val venue = event.get("venue")?.asString ?: return null
    val country = event.get("countryCode")?.asString ?: return null

    val offTime = utcToLondon(startUtc) ?: return null
    return Race(
        raceId = marketId,
        venue = venue,
        country = country,
        offTime = offTime,
        winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$marketId",
    )
}

internal fun utcToLondon(isoUtc: String): String? = try {
    val parsed = OffsetDateTime.parse(isoUtc)
    parsed.atZoneSameInstant(LONDON).toOffsetDateTime()
        .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
} catch (e: Exception) {
    null
}

/**
 * Parses a single `MarketBook` JSON object into a [MarketBookSnapshot].
 * Status is `OPEN` only when the market is live; anything else
 * (`SUSPENDED`, `CLOSED`, unknown) collapses to `OTHER` and the caller
 * treats the market as a failed scrape.
 */
fun layPricesFromBook(json: String): MarketBookSnapshot {
    val root = JsonParser.parseString(json).asJsonObject
    return layPricesFromBook(root)
}

internal fun layPricesFromBook(root: JsonObject): MarketBookSnapshot {
    val status = if (root.get("status")?.asString == "OPEN") MarketBookStatus.OPEN
                 else MarketBookStatus.OTHER
    if (status != MarketBookStatus.OPEN) {
        return MarketBookSnapshot(status, emptyMap())
    }
    val runners = root.get("runners")?.asJsonArray ?: return MarketBookSnapshot(status, emptyMap())
    val out = linkedMapOf<Long, Double?>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val sel = r.get("selectionId")?.asLong ?: continue
        val ex = r.get("ex")?.takeIf { it.isJsonObject }?.asJsonObject
        val lays = ex?.get("availableToLay")?.takeIf { it.isJsonArray }?.asJsonArray
        val firstPrice: Double? = lays?.firstOrNull { it.isJsonObject }
            ?.asJsonObject?.get("price")?.asDouble
        out[sel] = firstPrice
    }
    return MarketBookSnapshot(status, out)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairResponsesTest'`

Expected: 10 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 10.

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/BetfairResponses.kt src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt
git commit -m "Add pure parsers: parseSsoid, raceFromCatalogue, layPricesFromBook"
```

---

## Task 6: Request builders + `BetfairClient.kt`

Pure request-body builders (TDD) plus a thin HTTP transport that uses them. The HTTP transport itself is not unit-tested; everything inside it that has logic is broken out into pure helpers.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/BetfairResponses.kt` (add request-body builders next to the parsers — they're the same conceptual unit)
- Modify: `src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt` (extend with builder tests)
- Create: `src/main/kotlin/com/horsey/scraper/BetfairClient.kt`

> The builders live in the same file as the parsers because they're paired (one builds the wire format we send; the other parses the wire format we receive). Adding two more files for what's ~30 LOC of logic creates more cognitive load than it saves.

- [ ] **Step 1: Write failing tests for the request-body builders**

Append to `src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt`, just before its closing `}`:

```kotlin
    // --- buildLoginBody ---
    @Test
    fun `buildLoginBody url-encodes form fields`() {
        val body = buildLoginBody(username = "alice@example.com", password = "p@ss w&d")
        // Order is fixed for stability across JVMs.
        assertEquals(
            "username=alice%40example.com&password=p%40ss+w%26d",
            body
        )
    }

    // --- buildCatalogueBody ---
    @Test
    fun `buildCatalogueBody emits expected JSON-RPC body for WIN markets`() {
        val body = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = listOf("GB", "IE"),
            from = "2026-05-09T00:00:00Z",
            to   = "2026-05-10T00:00:00Z",
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val root = com.google.gson.JsonParser.parseString(body).asJsonObject
        val filter = root.getAsJsonObject("filter")
        assertEquals("[\"7\"]", filter.getAsJsonArray("eventTypeIds").toString())
        assertEquals("[\"WIN\"]", filter.getAsJsonArray("marketTypeCodes").toString())
        assertEquals("[\"GB\",\"IE\"]", filter.getAsJsonArray("marketCountries").toString())
        assertEquals("2026-05-09T00:00:00Z",
            filter.getAsJsonObject("marketStartTime").get("from").asString)
        assertEquals("1000", root.get("maxResults").asString)
        assertEquals("FIRST_TO_START", root.get("sort").asString)
    }

    // --- buildBookBody ---
    @Test
    fun `buildBookBody emits marketIds and EX_BEST_OFFERS priceData`() {
        val body = buildBookBody(listOf("1.1", "1.2"))
        val root = com.google.gson.JsonParser.parseString(body).asJsonObject
        assertEquals("[\"1.1\",\"1.2\"]", root.getAsJsonArray("marketIds").toString())
        assertEquals("[\"EX_BEST_OFFERS\"]",
            root.getAsJsonObject("priceProjection").getAsJsonArray("priceData").toString())
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairResponsesTest'`

Expected: FAIL with unresolved references for `buildLoginBody`, `buildCatalogueBody`, `buildBookBody`.

- [ ] **Step 3: Add the new imports to `BetfairResponses.kt`**

Open `src/main/kotlin/com/horsey/scraper/BetfairResponses.kt`. At the top of the file, add these three import lines to the existing import block (in alphabetical order relative to what's already there):

```kotlin
import com.google.gson.JsonArray
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
```

- [ ] **Step 4: Append the builders to `BetfairResponses.kt`**

At the bottom of the same file, append:

```kotlin
/**
 * Builds the `application/x-www-form-urlencoded` body for the interactive
 * login endpoint. URL-encodes both fields.
 */
fun buildLoginBody(username: String, password: String): String {
    fun enc(s: String) = URLEncoder.encode(s, StandardCharsets.UTF_8)
    return "username=${enc(username)}&password=${enc(password)}"
}

/**
 * Builds the JSON body for `listMarketCatalogue`. Always pins `eventTypeIds`
 * to `["7"]` (horse racing). All other axes are caller-controlled.
 */
fun buildCatalogueBody(
    marketTypeCodes: List<String>,
    countries: List<String>,
    from: String,
    to: String,
    projection: List<String>,
    maxResults: Int,
    sort: String,
): String {
    val filter = JsonObject().apply {
        add("eventTypeIds", JsonArray().apply { add("7") })
        add("marketTypeCodes", JsonArray().apply { marketTypeCodes.forEach { add(it) } })
        add("marketCountries", JsonArray().apply { countries.forEach { add(it) } })
        add("marketStartTime", JsonObject().apply {
            addProperty("from", from)
            addProperty("to", to)
        })
    }
    val root = JsonObject().apply {
        add("filter", filter)
        add("marketProjection", JsonArray().apply { projection.forEach { add(it) } })
        addProperty("maxResults", maxResults.toString())
        addProperty("sort", sort)
    }
    return root.toString()
}

/** Builds the JSON body for `listMarketBook` over up to 40 marketIds. */
fun buildBookBody(marketIds: List<String>): String {
    require(marketIds.size in 1..40) {
        "buildBookBody: marketIds size must be 1..40 (got ${marketIds.size})"
    }
    val root = JsonObject().apply {
        add("marketIds", JsonArray().apply { marketIds.forEach { add(it) } })
        add("priceProjection", JsonObject().apply {
            add("priceData", JsonArray().apply { add("EX_BEST_OFFERS") })
        })
    }
    return root.toString()
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.BetfairResponsesTest'`

Expected: 13 tests PASS (10 from Task 5 + 3 new).

- [ ] **Step 6: Implement `BetfairClient.kt`**

Create `src/main/kotlin/com/horsey/scraper/BetfairClient.kt`:

```kotlin
package com.horsey.scraper

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

private const val LOGIN_URL     = "https://identitysso.betfair.com/api/login"
private const val CATALOGUE_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/"
private const val BOOK_URL      = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/"

/**
 * Thin REST client for the three Betfair Exchange endpoints we use.
 *
 * Construct with the app key only. Call [login] once with username/password
 * — it stores the returned ssoid and uses it for every subsequent call.
 *
 * Errors:
 * - Login failures throw `IllegalStateException` (status surfaced).
 * - HTTP errors (non-2xx) throw `IllegalStateException` with the status code
 *   and the first 500 chars of the body.
 *
 * Retries: none. The caller decides what to drop on transient failures.
 */
class BetfairClient(
    private val appKey: String,
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build(),
) {
    private var ssoid: String? = null

    fun login(username: String, password: String) {
        val req = HttpRequest.newBuilder()
            .uri(URI.create(LOGIN_URL))
            .timeout(Duration.ofSeconds(15))
            .header("X-Application", appKey)
            .header("Accept", "application/json")
            .header("Content-Type", "application/x-www-form-urlencoded")
            .POST(HttpRequest.BodyPublishers.ofString(buildLoginBody(username, password)))
            .build()
        val body = sendForBody(req)
        ssoid = parseSsoid(body)
    }

    fun listMarketCatalogue(body: String): String {
        val req = bettingRequest(CATALOGUE_URL, body)
        return sendForBody(req)
    }

    fun listMarketBook(body: String): String {
        val req = bettingRequest(BOOK_URL, body)
        return sendForBody(req)
    }

    private fun bettingRequest(url: String, body: String): HttpRequest {
        val token = ssoid ?: error("BetfairClient: must call login() before betting endpoints")
        return HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(30))
            .header("X-Application", appKey)
            .header("X-Authentication", token)
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()
    }

    private fun sendForBody(req: HttpRequest): String {
        val res: HttpResponse<String> = http.send(req, HttpResponse.BodyHandlers.ofString())
        if (res.statusCode() / 100 != 2) {
            val snip = res.body().take(500)
            error("HTTP ${res.statusCode()} from ${req.uri()}: $snip")
        }
        return res.body()
    }
}
```

- [ ] **Step 7: Verify it compiles**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 8: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 3 (only the new builder tests added in this task).

- [ ] **Step 9: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/BetfairResponses.kt src/main/kotlin/com/horsey/scraper/BetfairClient.kt src/test/kotlin/com/horsey/scraper/BetfairResponsesTest.kt
git commit -m "Add BetfairClient + request-body builders for login/catalogue/book"
```

---

## Task 7: `RaceListFetcher.kt`

Wires `Regions` + `BetfairClient.listMarketCatalogue` + `raceFromCatalogue` to produce a `List<Race>` for today's WIN markets. The fetcher itself is thin (one call, then parse); the meaty logic is already covered by `BetfairResponsesTest`. We unit-test the time-window helper and the response-list shredding.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RaceListFetcher.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RaceListFetcherTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RaceListFetcherTest.kt`:

```kotlin
package com.horsey.scraper

import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RaceListFetcherTest {
    @Test
    fun `londonDayWindowUtc returns midnight-to-midnight London-local in UTC for a BST day`() {
        // 2026-05-11: BST, London is UTC+1. So midnight London = 23:00 prev UTC.
        val (from, to) = londonDayWindowUtc(LocalDate.parse("2026-05-11"))
        assertEquals("2026-05-10T23:00:00Z", from)
        assertEquals("2026-05-11T23:00:00Z", to)
    }

    @Test
    fun `londonDayWindowUtc returns midnight-to-midnight London-local in UTC for a GMT day`() {
        // 2026-01-15: GMT, London is UTC+0.
        val (from, to) = londonDayWindowUtc(LocalDate.parse("2026-01-15"))
        assertEquals("2026-01-15T00:00:00Z", from)
        assertEquals("2026-01-16T00:00:00Z", to)
    }

    @Test
    fun `parseCatalogueRaces shreds a list response into Race objects`() {
        val json = """
        [
          {
            "marketId": "1.1",
            "marketName": "5f Hcap",
            "marketStartTime": "2026-05-09T12:30:00.000Z",
            "description": { "marketType": "WIN", "numberOfWinners": 1 },
            "event": { "id": "10", "countryCode": "GB", "venue": "Lingfield" }
          },
          {
            "marketId": "1.2",
            "marketName": "Mdn",
            "marketStartTime": "2026-05-09T13:00:00.000Z",
            "description": { "marketType": "WIN", "numberOfWinners": 1 },
            "event": { "id": "20", "countryCode": "IE", "venue": "Naas" }
          }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(2, races.size)
        assertEquals("1.1", races[0].raceId)
        assertEquals("Naas", races[1].venue)
        assertEquals("IE", races[1].country)
    }

    @Test
    fun `parseCatalogueRaces sorts by offTime then venue and dedupes`() {
        val json = """
        [
          { "marketId": "1.B", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "GB", "venue": "Bath" } },
          { "marketId": "1.A", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "10", "countryCode": "GB", "venue": "Lingfield" } },
          { "marketId": "1.B", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "GB", "venue": "Bath" } }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(listOf("1.A", "1.B"), races.map { it.raceId })
    }

    @Test
    fun `parseCatalogueRaces skips entries with missing required fields`() {
        val json = """
        [
          { "marketId": "1.1", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "10", "countryCode": "GB" } },
          { "marketId": "1.2", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "IE", "venue": "Naas" } }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(listOf("1.2"), races.map { it.raceId })
    }

    @Test
    fun `parseCatalogueRaces returns empty on empty array`() {
        assertTrue(parseCatalogueRaces("[]").isEmpty())
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceListFetcherTest'`

Expected: FAIL with unresolved references for `londonDayWindowUtc`, `parseCatalogueRaces`.

- [ ] **Step 3: Implement `RaceListFetcher.kt`**

Create `src/main/kotlin/com/horsey/scraper/RaceListFetcher.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.JsonParser
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val LONDON_ZONE = ZoneId.of("Europe/London")
private val UTC_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'")

/**
 * Returns `(fromUtc, toUtc)` as ISO-8601 `Z` strings for the 24-hour day
 * that starts at midnight Europe/London on [date].
 *
 * In May (BST, UTC+1): `("2026-05-10T23:00:00Z", "2026-05-11T23:00:00Z")`.
 * In January (GMT, UTC+0): `("2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z")`.
 */
fun londonDayWindowUtc(date: LocalDate): Pair<String, String> {
    val from = date.atStartOfDay(LONDON_ZONE).toInstant()
    val to = date.plusDays(1).atStartOfDay(LONDON_ZONE).toInstant()
    return from.atZone(ZoneId.of("UTC")).format(UTC_FMT) to
           to.atZone(ZoneId.of("UTC")).format(UTC_FMT)
}

/**
 * Shreds a `listMarketCatalogue` JSON array response into `Race`s.
 * Skips entries that don't contain the fields required by [raceFromCatalogue].
 * Dedupes by `raceId` (first wins) and sorts by `(offTime, venue)`.
 */
fun parseCatalogueRaces(json: String): List<Race> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = mutableListOf<Race>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val race = raceFromCatalogue(el.asJsonObject) ?: continue
        out += race
    }
    return out.distinctBy { it.raceId }
              .sortedWith(compareBy({ it.offTime }, { it.venue }))
}

/**
 * Calls `listMarketCatalogue` once for today's WIN markets in the union of
 * [regions]' country codes, and returns the resulting `Race` list.
 */
class RaceListFetcher(private val client: BetfairClient) {
    fun fetch(regions: Set<String>, today: LocalDate = LocalDate.now(LONDON_ZONE)): List<Race> {
        val (from, to) = londonDayWindowUtc(today)
        val countries = Regions.countriesForAll(regions).sorted()
        val body = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = countries,
            from = from,
            to = to,
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val response = client.listMarketCatalogue(body)
        return parseCatalogueRaces(response)
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceListFetcherTest'`

Expected: 6 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 6.

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RaceListFetcher.kt src/test/kotlin/com/horsey/scraper/RaceListFetcherTest.kt
git commit -m "Add RaceListFetcher: today's WIN markets via listMarketCatalogue"
```

---

## Task 8: `RaceOddsFetcher.kt`

Wires the second catalogue call (PLACE markets), `MarketClassifier`, batched `listMarketBook` calls, and the existing `pivotMarketScrapes` to produce a `List<RaceOdds>`. The orchestration is thin; the pure shredding/joining is covered by tests.

**Files:**
- Create: `src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt`
- Create: `src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt`:

```kotlin
package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RaceOddsFetcherTest {
    @Test
    fun `chunkOf40 chunks lists into groups of 40`() {
        assertEquals(emptyList(), chunkOf40(emptyList()))
        assertEquals(listOf((1..40).toList()), chunkOf40((1..40).toList()))
        val ninety = (1..90).toList()
        val chunks = chunkOf40(ninety)
        assertEquals(3, chunks.size)
        assertEquals(40, chunks[0].size)
        assertEquals(40, chunks[1].size)
        assertEquals(10, chunks[2].size)
    }

    @Test
    fun `parseCataloguePlaceMarkets classifies and joins to eventId`() {
        val json = """
        [
          {
            "marketId": "1.10", "marketName": "Top 2 Finish",
            "description": { "marketType": "PLACE", "numberOfWinners": 2 },
            "event": { "id": "EVT1" },
            "runners": [
              { "selectionId": 100, "runnerName": "Some Horse" },
              { "selectionId": 200, "runnerName": "Outsider Bob" }
            ]
          },
          {
            "marketId": "1.11", "marketName": "To Be Placed",
            "description": { "marketType": "PLACE", "numberOfWinners": 3 },
            "event": { "id": "EVT1" },
            "runners": []
          },
          {
            "marketId": "1.12", "marketName": "Top 3 Finish",
            "description": { "marketType": "PLACE", "numberOfWinners": 3 },
            "event": { "id": "EVT1" },
            "runners": [ { "selectionId": 100, "runnerName": "Some Horse" } ]
          }
        ]
        """.trimIndent()
        val byEvent = parseCataloguePlaceMarkets(json)
        assertEquals(setOf("EVT1"), byEvent.keys)
        val markets = byEvent.getValue("EVT1").associateBy { it.type }
        assertEquals(setOf(MarketType.TOP_2, MarketType.TOP_3), markets.keys)
        assertEquals("1.10", markets.getValue(MarketType.TOP_2).marketId)
        assertEquals(mapOf(100L to "Some Horse", 200L to "Outsider Bob"),
            markets.getValue(MarketType.TOP_2).runners)
    }

    @Test
    fun `parseWinCatalogueRunners returns selectionId-ordered runner names per marketId`() {
        val json = """
        [
          {
            "marketId": "1.1", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "EVT1", "countryCode": "GB", "venue": "Lingfield" },
            "runners": [
              { "selectionId": 100, "runnerName": "Some Horse", "sortPriority": 1 },
              { "selectionId": 200, "runnerName": "Outsider Bob", "sortPriority": 2 }
            ]
          }
        ]
        """.trimIndent()
        val byMarket = parseWinCatalogueRunners(json)
        val runners = byMarket.getValue("1.1")
        assertEquals(listOf(100L to "Some Horse", 200L to "Outsider Bob"), runners)
    }

    @Test
    fun `parseBookSnapshots produces a snapshot per marketId`() {
        val json = """
        [
          { "marketId": "1.1", "status": "OPEN",
            "runners": [ { "selectionId": 100, "ex": { "availableToLay": [{ "price": 4.8 }] } } ] },
          { "marketId": "1.2", "status": "SUSPENDED", "runners": [] }
        ]
        """.trimIndent()
        val snaps = parseBookSnapshots(json)
        assertEquals(MarketBookStatus.OPEN, snaps.getValue("1.1").status)
        assertEquals(4.8, snaps.getValue("1.1").layBySelectionId[100L])
        assertEquals(MarketBookStatus.OTHER, snaps.getValue("1.2").status)
    }

    @Test
    fun `joinScrapes drops races whose WIN is OTHER`() {
        val race = race("1.W", "Lingfield")
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = emptyMap(),
            snapshots = mapOf("1.W" to MarketBookSnapshot(MarketBookStatus.OTHER, emptyMap())),
            winRunners = mapOf("1.W" to emptyList()),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertTrue(out.isEmpty())
    }

    @Test
    fun `joinScrapes builds a RaceOdds with WIN-only when no PLACE markets present`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(
            MarketBookStatus.OPEN,
            mapOf(100L to 4.8, 200L to null),
        )
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = emptyMap(),
            snapshots = mapOf("1.W" to winSnap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse", 200L to "Outsider Bob")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertEquals(1, out.size)
        val odds = out[0]
        assertEquals(setOf(MarketType.WIN), odds.marketScrapedAt.keys)
        assertEquals("2026-05-09T12:00:00Z", odds.marketScrapedAt[MarketType.WIN])
        assertEquals(listOf("Some Horse", "Outsider Bob"), odds.runners.map { it.name })
        assertEquals(mapOf(MarketType.WIN to 4.8), odds.runners[0].lay)
    }

    @Test
    fun `joinScrapes pivots WIN plus a successful TOP_2`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 4.8))
        val top2Snap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 2.5))
        val placeMarkets = mapOf("1.W" to listOf(
            PlaceMarketEntry("1.P", MarketType.TOP_2, mapOf(100L to "Some Horse"))
        ))
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = placeMarkets,
            snapshots = mapOf("1.W" to winSnap, "1.P" to top2Snap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertEquals(1, out.size)
        val odds = out[0]
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_2), odds.marketScrapedAt.keys)
        assertEquals(mapOf(MarketType.WIN to 4.8, MarketType.TOP_2 to 2.5), odds.runners[0].lay)
    }

    @Test
    fun `joinScrapes drops a TOP_N where the book is OTHER`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 4.8))
        val top2Snap = MarketBookSnapshot(MarketBookStatus.OTHER, emptyMap())
        val placeMarkets = mapOf("1.W" to listOf(
            PlaceMarketEntry("1.P", MarketType.TOP_2, mapOf(100L to "Some Horse"))
        ))
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = placeMarkets,
            snapshots = mapOf("1.W" to winSnap, "1.P" to top2Snap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        val odds = out.single()
        assertEquals(setOf(MarketType.WIN), odds.marketScrapedAt.keys)
        assertNull(odds.runners[0].lay[MarketType.TOP_2])
    }

    private fun race(raceId: String, venue: String) =
        Race(
            raceId = raceId,
            venue = venue,
            country = "GB",
            offTime = "2026-05-09T13:30:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$raceId",
        )
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceOddsFetcherTest'`

Expected: FAIL with unresolved references for `chunkOf40`, `parseCataloguePlaceMarkets`, `parseWinCatalogueRunners`, `parseBookSnapshots`, `joinScrapes`, `PlaceMarketEntry`.

- [ ] **Step 3: Implement `RaceOddsFetcher.kt`**

Create `src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt`:

```kotlin
package com.horsey.scraper

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.time.Instant

data class PlaceMarketEntry(
    val marketId: String,
    val type: MarketType,
    /** selectionId → runnerName, as published by the catalogue for this market. */
    val runners: Map<Long, String>,
)

/** Splits a list into chunks of at most 40 elements (Betfair's `listMarketBook` cap). */
fun <T> chunkOf40(items: List<T>): List<List<T>> =
    if (items.isEmpty()) emptyList() else items.chunked(40)

/**
 * Parses a PLACE `listMarketCatalogue` response: classifies each market via
 * [classifyTopN] and groups the survivors by `event.id`. Anything that
 * doesn't classify (To Be Placed, mismatched winners, etc.) is dropped.
 */
fun parseCataloguePlaceMarkets(json: String): Map<String, List<PlaceMarketEntry>> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, MutableList<PlaceMarketEntry>>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val name = root.get("marketName")?.asString ?: continue
        val desc = root.get("description")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        val numberOfWinners = desc.get("numberOfWinners")?.asInt ?: continue
        val type = classifyTopN(name, numberOfWinners) ?: continue
        val marketId = root.get("marketId")?.asString ?: continue
        val eventId = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject
            ?.get("id")?.asString ?: continue
        out.getOrPut(eventId) { mutableListOf() }.add(
            PlaceMarketEntry(marketId, type, runnerMap(root))
        )
    }
    return out
}

/**
 * Parses a WIN `listMarketCatalogue` response into a marketId → ordered list
 * of `(selectionId, runnerName)` pairs. Order is the catalogue order, which
 * matches the WIN page display order on the Betfair Exchange.
 */
fun parseWinCatalogueRunners(json: String): Map<String, List<Pair<Long, String>>> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, List<Pair<Long, String>>>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val marketId = root.get("marketId")?.asString ?: continue
        val runners = root.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray ?: continue
        val pairs = mutableListOf<Pair<Long, String>>()
        for (rEl in runners) {
            if (!rEl.isJsonObject) continue
            val r = rEl.asJsonObject
            val sel = r.get("selectionId")?.asLong ?: continue
            val name = r.get("runnerName")?.asString ?: continue
            pairs += sel to name
        }
        out[marketId] = pairs
    }
    return out
}

/** Parses a `listMarketBook` array response into marketId → snapshot. */
fun parseBookSnapshots(json: String): Map<String, MarketBookSnapshot> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, MarketBookSnapshot>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val marketId = root.get("marketId")?.asString ?: continue
        out[marketId] = layPricesFromBook(root)
    }
    return out
}

private fun runnerMap(catalogue: JsonObject): Map<Long, String> {
    val runners = catalogue.get("runners")?.takeIf { it.isJsonArray }?.asJsonArray ?: return emptyMap()
    val out = linkedMapOf<Long, String>()
    for (rEl in runners) {
        if (!rEl.isJsonObject) continue
        val r = rEl.asJsonObject
        val sel = r.get("selectionId")?.asLong ?: continue
        val name = r.get("runnerName")?.asString ?: continue
        out[sel] = name
    }
    return out
}

/**
 * Joins race metadata, catalogue runners, PLACE classifications, and price
 * snapshots into the final `List<RaceOdds>`. Rules mirror the Selenium
 * pipeline: WIN failure (`status != OPEN`) drops the race; any TOP_N with
 * `status != OPEN` is treated as a failed scrape (key omitted everywhere).
 *
 * Pure function: caller provides the single `scrapedAt` timestamp (captured
 * after all `listMarketBook` calls have returned) and the formatted
 * `winMarketName`.
 */
fun joinScrapes(
    races: List<Race>,
    placeMarketsByRaceId: Map<String, List<PlaceMarketEntry>>,
    snapshots: Map<String, MarketBookSnapshot>,
    winRunners: Map<String, List<Pair<Long, String>>>,
    winMarketName: String,
    scrapedAt: String,
): List<RaceOdds> {
    val out = mutableListOf<RaceOdds>()
    for (race in races) {
        val winSnap = snapshots[race.raceId] ?: continue
        if (winSnap.status != MarketBookStatus.OPEN) continue

        val nameOrder = winRunners[race.raceId] ?: continue
        val scrapes = linkedMapOf<MarketType, MarketScrape>(
            MarketType.WIN to MarketScrape(
                type = MarketType.WIN,
                scrapedAt = scrapedAt,
                runners = nameOrder.map { (sel, name) -> name to winSnap.layBySelectionId[sel] },
            )
        )

        val placeMarkets = placeMarketsByRaceId[race.raceId].orEmpty()
        for (place in placeMarkets) {
            val snap = snapshots[place.marketId] ?: continue
            if (snap.status != MarketBookStatus.OPEN) continue
            val rows = place.runners.entries.map { (sel, name) ->
                name to snap.layBySelectionId[sel]
            }
            scrapes[place.type] = MarketScrape(
                type = place.type,
                scrapedAt = scrapedAt,
                runners = rows,
            )
        }

        val odds = assembleRaceOdds(race, winMarketName, scrapes) ?: continue
        out += odds
    }
    return out
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.RaceOddsFetcherTest'`

Expected: 8 tests PASS.

- [ ] **Step 5: Add the live-orchestration `fetch()` method**

Append to `src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt` (before the file's terminal blank line):

```kotlin
/**
 * Fetches WIN + classified Top-N markets for the supplied races. Performs:
 *
 *  1. One catalogue call for PLACE markets in the same time window and
 *     country set as the races.
 *  2. One catalogue call for WIN markets (sources runner names, race-type
 *     snippet, and the marketId → eventId map used to join the PLACE
 *     results back to races).
 *  3. Batched `listMarketBook` calls (≤40 marketIds per chunk) covering the
 *     WIN + classified PLACE markets.
 *  4. One call to [joinScrapes] per race with a single shared `scrapedAt`
 *     timestamp captured immediately after the last book response.
 *
 * Per-race `marketName` is formatted with [formatMarketName]; the race-type
 * snippet comes from the WIN catalogue's `marketName` field.
 */
class RaceOddsFetcher(
    private val client: BetfairClient,
    private val nowProvider: () -> Instant = { Instant.now() },
) {
    fun fetch(races: List<Race>, regions: Set<String>): List<RaceOdds> {
        if (races.isEmpty()) return emptyList()
        val countries = Regions.countriesForAll(regions).sorted()
        val (from, to) = londonDayWindowUtc(java.time.LocalDate.now(java.time.ZoneId.of("Europe/London")))

        // PLACE catalogue.
        val placeBody = buildCatalogueBody(
            marketTypeCodes = listOf("PLACE"),
            countries = countries,
            from = from, to = to,
            projection = listOf("EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val placeJson = client.listMarketCatalogue(placeBody)
        val placeByEvent = parseCataloguePlaceMarkets(placeJson)

        // WIN catalogue (re-fetched to grab runners + raceType marketName).
        val winBody = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = countries,
            from = from, to = to,
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val winJson = client.listMarketCatalogue(winBody)
        val winRunners = parseWinCatalogueRunners(winJson)
        val winRaceTypeByRaceId = parseWinRaceTypes(winJson)
        val eventIdByRaceId = parseWinEventIds(winJson)

        // Rekey placeByEvent from eventId → raceId using the WIN catalogue's
        // marketId↔eventId map (built once, used many).
        val raceIdByEventId = eventIdByRaceId.entries.associate { (rid, eid) -> eid to rid }
        val placeByRaceId = mutableMapOf<String, List<PlaceMarketEntry>>()
        for ((eventId, list) in placeByEvent) {
            val raceId = raceIdByEventId[eventId] ?: continue
            placeByRaceId[raceId] = list
        }

        // Gather marketIds and fetch prices in batches.
        val allMarketIds = (races.map { it.raceId } +
            placeByRaceId.values.flatten().map { it.marketId }).distinct()
        val snapshots = linkedMapOf<String, MarketBookSnapshot>()
        for (chunk in chunkOf40(allMarketIds)) {
            val resp = client.listMarketBook(buildBookBody(chunk))
            snapshots.putAll(parseBookSnapshots(resp))
        }

        // Single timestamp captured after all book responses are in. The
        // resolution is coarser than per-batch, but matches the schema's
        // "scrapedAt = when we observed this market" semantics within the
        // few-hundred-ms it takes the book calls to complete.
        val scrapedAt = nowProvider().toString()

        val out = mutableListOf<RaceOdds>()
        for (race in races) {
            val raceType = winRaceTypeByRaceId[race.raceId] ?: ""
            val marketName = formatMarketName(race, raceType)
            out += joinScrapes(
                races = listOf(race),
                placeMarketsByRaceId = mapOf(race.raceId to (placeByRaceId[race.raceId] ?: emptyList())),
                snapshots = snapshots,
                winRunners = winRunners,
                winMarketName = marketName,
                scrapedAt = scrapedAt,
            )
        }
        return out
    }
}

/**
 * Returns marketId → its WIN catalogue `marketName` (used as the race-type
 * snippet for the spec's `"<HH:mm> <venue> - <race type>"` format).
 */
fun parseWinRaceTypes(json: String): Map<String, String> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, String>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val mid = root.get("marketId")?.asString ?: continue
        val name = root.get("marketName")?.asString ?: ""
        out[mid] = name
    }
    return out
}

/** Returns marketId → eventId from a WIN `listMarketCatalogue` response. */
fun parseWinEventIds(json: String): Map<String, String> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = linkedMapOf<String, String>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val root = el.asJsonObject
        val mid = root.get("marketId")?.asString ?: continue
        val event = root.get("event")?.takeIf { it.isJsonObject }?.asJsonObject ?: continue
        val eid = event.get("id")?.asString ?: continue
        out[mid] = eid
    }
    return out
}
```

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: previous total + 8 (the new `RaceOddsFetcherTest` tests). The new orchestration methods are not unit-tested directly — the pure helpers under them are.

- [ ] **Step 7: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/RaceOddsFetcher.kt src/test/kotlin/com/horsey/scraper/RaceOddsFetcherTest.kt
git commit -m "Add RaceOddsFetcher: catalogue + book + join, batched ≤40 ids"
```

---

## Task 9: Rewrite `Main.kt` to use the API path

Switch `main` to: load credentials → login → `RaceListFetcher.fetch` → `RaceOddsFetcher.fetch` → write `data.json`. Drop the call to `parseWorkerCount` and `scrapeRacesInParallel`. The old scraper classes still exist (deleted in Task 11) — `Main.kt` simply stops referencing them.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt`

- [ ] **Step 1: Replace `Main.kt` end-to-end**

Open `src/main/kotlin/com/horsey/scraper/Main.kt`. Replace the **entire file** (preserving the package declaration and `OUTPUT_FILE` constant) with:

```kotlin
package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.Instant

private const val OUTPUT_FILE = "data.json"

/**
 * Parses the regions CLI argument. First positional arg is a
 * comma-separated set of region IDs (case-insensitive, whitespace-tolerant).
 * If absent, defaults to `setOf("gb-ie")`.
 *
 * Region IDs come from [Regions.ALL]. Unknown IDs throw
 * `IllegalArgumentException` whose message lists the bad id(s) alongside
 * the valid set, so the caller can surface a clean error. An empty arg
 * (or one that parses to no ids) also throws.
 */
fun parseRegions(args: Array<String>): Set<String> {
    val raw = args.getOrNull(0) ?: return setOf("gb-ie")
    val ids = raw.split(",").map { it.trim().lowercase() }
        .filter { it.isNotEmpty() }
        .toSet()
    val known = Regions.ALL
    val unknown = ids - known
    require(unknown.isEmpty()) {
        "unknown region(s) ${unknown.joinToString(",")}; valid: ${known.sorted().joinToString(",")}"
    }
    require(ids.isNotEmpty()) {
        "regions must be non-empty; valid: ${known.sorted().joinToString(",")}"
    }
    return ids
}

/**
 * Entry point: one pass over today's racing in the chosen regions, fetched
 * from the Betfair Exchange REST API.
 *
 *   1. Parses regions from args[0] (default `gb-ie`).
 *   2. Loads credentials from `~/.horsey-scraper/credentials.json`.
 *   3. Logs in to identitysso.
 *   4. Fetches today's WIN markets and the explicit Top-N markets, then
 *      their prices in batches of ≤40 marketIds.
 *   5. Pivots into per-horse lay map and writes `data.json`.
 *
 * Output schema: see docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md
 * Migration:     see docs/superpowers/specs/2026-05-11-betfair-api-migration-design.md
 */
fun main(args: Array<String>) {
    val regions = try {
        parseRegions(args)
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    val credentials = try {
        loadCredentials(defaultCredentialsPath())
    } catch (e: IllegalArgumentException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(2)
    }

    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()

    println("Horsey Scraper — Betfair Exchange API — multi-market lay")
    println("regions=${regions.sorted().joinToString(",")}")
    println("=".repeat(80))

    val runStart = Instant.now()
    val client = BetfairClient(appKey = credentials.appKey)
    try {
        client.login(credentials.username, credentials.password)
    } catch (e: IllegalStateException) {
        System.err.println("Error: ${e.message}")
        kotlin.system.exitProcess(1)
    }

    println("\n[$runStart] Fetching today's race list…")
    val races = try {
        RaceListFetcher(client).fetch(regions)
    } catch (e: Exception) {
        System.err.println("Error fetching race list: ${e.message}")
        kotlin.system.exitProcess(1)
    }
    println("Found ${races.size} races today.")
    races.forEach { println("  ${it.offTime}  ${it.country}  ${it.venue}  (${it.raceId})") }

    val results: List<RaceOdds> = try {
        RaceOddsFetcher(client).fetch(races, regions)
    } catch (e: Exception) {
        System.err.println("Error fetching odds: ${e.message}")
        emptyList()
    }

    for (odds in results) {
        val markets = odds.marketScrapedAt.keys.joinToString(",") { it.name }
        println("  ${odds.offTime} ${odds.venue} (${odds.raceId}) → ${odds.runners.size} runners, markets=[$markets]")
    }
    val dropped = races.filter { r -> results.none { it.raceId == r.raceId } }
    for (r in dropped) {
        println("  ${r.offTime} ${r.venue} (${r.raceId}) DROPPED")
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

Expected: `BUILD SUCCESSFUL`. (The old scraper classes still exist but are unused; that's intentional — Task 11 deletes them.)

- [ ] **Step 3: Run the full suite**

Run: `./gradlew test`

Expected: previous total. No new tests, no regressions.

- [ ] **Step 4: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/Main.kt
git commit -m "Main.kt: use BetfairClient + Race(List|Odds)Fetcher path"
```

---

## Task 10: Update `run.sh`

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh`**

Replace the entire contents of `run.sh` with:

```bash
#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
exec ./gradlew run --quiet --args="${1:-gb-ie}"
```

- [ ] **Step 2: Verify the script syntax**

Run: `bash -n run.sh`

Expected: no output, exit code 0.

- [ ] **Step 3: Verify the executable bit**

Run: `ls -l run.sh`

Expected: the mode column shows `x` for the user. If not, restore with `chmod +x run.sh`.

- [ ] **Step 4: Commit**

```bash
git add run.sh
git commit -m "run.sh: single regions arg, default gb-ie"
```

---

## Task 11: Delete obsolete files

Now that `Main.kt` no longer references the Selenium scraper or `RaceWorkerPool`, delete every Selenium-touched file and the now-stranded test files.

**Files (delete all):**
- `src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt`
- `src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt`
- `src/main/kotlin/com/horsey/scraper/MarketScraper.kt`
- `src/main/kotlin/com/horsey/scraper/RelatedMarketsFinder.kt`
- `src/main/kotlin/com/horsey/scraper/WebDriverUtils.kt`
- `src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt`
- `src/main/kotlin/com/horsey/scraper/Venues.kt`
- `src/main/kotlin/com/horsey/scraper/DebugListMain.kt`
- `src/main/kotlin/com/horsey/scraper/DebugMarketLinks.kt`
- `src/main/kotlin/com/horsey/scraper/DebugMarketName.kt`
- `src/main/kotlin/com/horsey/scraper/TestListMain.kt`
- `src/main/kotlin/com/horsey/scraper/TestRaceMain.kt`
- `src/test/kotlin/com/horsey/scraper/BetfairRaceListScraperTest.kt`
- `src/test/kotlin/com/horsey/scraper/BetfairRaceScraperAssemblyTest.kt`
- `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt`
- `debug-page.html`

- [ ] **Step 1: Delete the main-source files**

Run:

```bash
git rm \
  src/main/kotlin/com/horsey/scraper/BetfairRaceListScraper.kt \
  src/main/kotlin/com/horsey/scraper/BetfairRaceScraper.kt \
  src/main/kotlin/com/horsey/scraper/MarketScraper.kt \
  src/main/kotlin/com/horsey/scraper/RelatedMarketsFinder.kt \
  src/main/kotlin/com/horsey/scraper/WebDriverUtils.kt \
  src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt \
  src/main/kotlin/com/horsey/scraper/Venues.kt \
  src/main/kotlin/com/horsey/scraper/DebugListMain.kt \
  src/main/kotlin/com/horsey/scraper/DebugMarketLinks.kt \
  src/main/kotlin/com/horsey/scraper/DebugMarketName.kt \
  src/main/kotlin/com/horsey/scraper/TestListMain.kt \
  src/main/kotlin/com/horsey/scraper/TestRaceMain.kt
```

- [ ] **Step 2: Delete the test files**

Run:

```bash
git rm \
  src/test/kotlin/com/horsey/scraper/BetfairRaceListScraperTest.kt \
  src/test/kotlin/com/horsey/scraper/BetfairRaceScraperAssemblyTest.kt \
  src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt
```

- [ ] **Step 3: Delete `debug-page.html`**

Run: `git rm debug-page.html`

- [ ] **Step 4: Verify nothing else imports the deleted code**

Run: `grep -rn "import com.horsey.scraper.BetfairRaceListScraper\|import com.horsey.scraper.BetfairRaceScraper\|REGION_TABS\|RegionTab\b\|Venues\b\|RaceWorkerPool\|scrapeRacesInParallel\|createChromeDriver\|findTopNUrls\|scrapeLoadedMarket\|parseWorkerCount" src/`

Expected: no matches. If anything matches, investigate before continuing — likely a leftover reference inside one of the new files.

- [ ] **Step 5: Verify the project still compiles**

Run: `./gradlew compileKotlin compileTestKotlin`

Expected: `BUILD SUCCESSFUL`. If a test still references Selenium symbols, the message will name the offending file — go back and clean it up.

- [ ] **Step 6: Run the full suite**

Run: `./gradlew test`

Expected: every test passes. The total drops by the number of tests in the three deleted test files (the legacy scraper, assembly, and worker-pool tests).

- [ ] **Step 7: Commit**

```bash
git commit -m "Drop Selenium scraper, worker pool, debug mains, and their tests"
```

---

## Task 12: Drop Selenium and slf4j from `build.gradle.kts`

**Files:**
- Modify: `build.gradle.kts`

- [ ] **Step 1: Remove the Selenium and slf4j dependencies**

Open `build.gradle.kts`. Find the `dependencies { … }` block:

```kotlin
dependencies {
    implementation("org.seleniumhq.selenium:selenium-java:4.16.1")
    implementation("org.slf4j:slf4j-simple:2.0.9")
    implementation("com.google.code.gson:gson:2.10.1")

    testImplementation(kotlin("test"))
    // Gradle 9 requires explicit junit-platform-console for useJUnitPlatform() test task discovery
    testRuntimeOnly("org.junit.platform:junit-platform-console:1.9.3")
}
```

Replace with:

```kotlin
dependencies {
    implementation("com.google.code.gson:gson:2.10.1")

    testImplementation(kotlin("test"))
    // Gradle 9 requires explicit junit-platform-console for useJUnitPlatform() test task discovery
    testRuntimeOnly("org.junit.platform:junit-platform-console:1.9.3")
}
```

- [ ] **Step 2: Confirm Selenium really is gone from the resolved classpath**

Run: `./gradlew dependencies --configuration runtimeClasspath | grep -E 'selenium|slf4j'`

Expected: no output. If Selenium appears (e.g. pulled in transitively somewhere unexpected), stop and investigate.

- [ ] **Step 3: Run the full suite**

Run: `./gradlew test`

Expected: every test passes.

- [ ] **Step 4: Compile + run target reachable**

Run: `./gradlew compileKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: Commit**

```bash
git add build.gradle.kts
git commit -m "Drop Selenium and slf4j-simple from build.gradle.kts"
```

---

## Task 13: `.gitignore` for credentials defence-in-depth

**Files:**
- Modify (or create): `.gitignore`

- [ ] **Step 1: Inspect current state**

Run: `cat .gitignore 2>/dev/null || echo "MISSING"`

Note what's already there.

- [ ] **Step 2: Append defensive entries**

If `.gitignore` exists, append. If not, create. Either way, ensure the following lines are present (deduplicate if `.gradle/` or `build/` are already there):

```
# Credentials — never commit. Real file lives at ~/.horsey-scraper/credentials.json.
credentials.json
*.env

# Gradle / IntelliJ noise
.gradle/
build/
.idea/
*.iml
```

If your existing `.gitignore` already covers gradle/IntelliJ noise, only add the credentials lines:

```
# Credentials — never commit. Real file lives at ~/.horsey-scraper/credentials.json.
credentials.json
*.env
```

- [ ] **Step 3: Verify**

Run: `git check-ignore -v credentials.json`

Expected: a line like `.gitignore:N:credentials.json    credentials.json` (matched).

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "gitignore: credentials.json and .env files (defence-in-depth)"
```

---

## Task 14: Add `README.md`

A short README documenting prerequisites, credentials file, and CLI usage.

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

Create `README.md` at repo root with this content:

````markdown
# Horsey Scraper

One-shot CLI that fetches today's UK + Irish horse-racing lay-side prices
from the Betfair Exchange API and writes them to `data.json`.

## Prerequisites

- A Betfair account with **2FA disabled**. Interactive login fails
  (`LOGIN_RESTRICTED`) on 2FA-enabled accounts.
- A Betfair developer **app key** (live, not delayed).
- JDK 17.

## Credentials

Create `~/.horsey-scraper/credentials.json`:

```json
{
  "username": "your-betfair-username",
  "password": "your-betfair-password",
  "appKey": "your-app-key"
}
```

Recommended: `chmod 600 ~/.horsey-scraper/credentials.json`. The scraper
warns to stderr if the file is readable by group/others.

## Usage

```
./run.sh               # GB + IE (default)
./run.sh us            # US only
./run.sh gb-ie,us      # both
```

Output is written to `./data.json`. Schema is documented in
`docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md`.

## Validating output

```
./gradlew run --quiet -PmainClass=com.horsey.scraper.ValidateMainKt --args=data.json
```

## Architecture

- `BetfairClient` — login + two betting endpoints (catalogue, book).
- `RaceListFetcher` — today's WIN markets in selected regions.
- `RaceOddsFetcher` — PLACE markets classified as Top-N + batched prices.
- `RunnerPivot` (unchanged) — flips per-market lay maps to per-runner.
- `SchemaValidator` (unchanged) — enforces the output contract.

Design docs live under `docs/superpowers/specs/` and implementation plans
under `docs/superpowers/plans/`.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README: prerequisites, credentials, usage"
```

---

## Task 15: Final validation

A quick set of guardrails to confirm the migration is complete.

- [ ] **Step 1: No Selenium references anywhere**

Run: `grep -rn -i 'selenium\|webdriver\|chromedriver' src/ build.gradle.kts`

Expected: no output.

- [ ] **Step 2: No references to removed types**

Run: `grep -rn 'BetfairRaceListScraper\|BetfairRaceScraper\|MarketScraper\|RelatedMarketsFinder\|WebDriverUtils\|RaceWorkerPool\|scrapeRacesInParallel\|Venues\b\|REGION_TABS\|RegionTab\b\|parseWorkerCount\|createChromeDriver' src/`

Expected: no output.

- [ ] **Step 3: Full test run**

Run: `./gradlew test 2>&1 | tail -20`

Expected: `BUILD SUCCESSFUL`. Note the new test total — record it for the user when reporting completion.

- [ ] **Step 4: Compile + run target reachable (smoke build, no execution)**

Run: `./gradlew compileKotlin compileTestKotlin assemble`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: CLI error path is wired (no live API call)**

Run: `./run.sh fr 2>&1 | head -5`

Expected: contains `Error: unknown region(s) fr; valid: gb-ie,us`. (Gradle "BUILD FAILED" noise after the error is expected.)

- [ ] **Step 6: Surface the live smoke step to the user**

Don't run a live scrape unattended — it requires the user's real
`~/.horsey-scraper/credentials.json`. Mention to the user:

> "Migration complete. To smoke-test live, ensure `~/.horsey-scraper/credentials.json` exists, run `./run.sh`, then validate the output with `./gradlew run --quiet -PmainClass=com.horsey.scraper.ValidateMainKt --args=data.json`. Expected: zero validator errors."

No commit in this task — it's pure validation.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Cert-based (non-interactive) login.** Required if 2FA is on. Spec-documented as future work.
- **Retries / rate-limit backoff.** Betfair's API has weight-based limits; if you start running this every few minutes a polite backoff becomes worth having.
- **Streaming API.** Real-time price updates are out of scope for a one-shot snapshot tool.
- **Storing ssoid across runs.** Each run logs in fresh; harmless for one-shot runs but a candidate optimisation if we ever loop.
- **Better marketName extraction.** API gives us richer fields (`event.openDate`, race-class, etc.) we currently ignore; the spec preserves the existing format.
- **Smoke run in CI.** Requires a credentials secret; out of scope here.
