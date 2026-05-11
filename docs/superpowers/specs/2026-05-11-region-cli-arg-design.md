---
status: draft
date: 2026-05-11
topic: Make scraped regions a CLI arg (default GB+IE only)
---

# Make scraped regions a CLI arg (default GB+IE only)

## Goal

Make region selection an explicit CLI argument so the scraper defaults to GB+IE only and doesn't pull US racing on every run. The user opts into US (or any future region) by listing it as the second positional arg to `run.sh`.

## Non-goals

- No per-country control within the GB+IE tab. The Betfair tab combines GB and IE; you take both or neither.
- No `--regions=` named flag. Positional, simple, mirrors the existing `[workers]` arg.
- No env-var fallback (`HORSEY_REGIONS=…`). YAGNI.
- No deprecation of the no-arg form. `./run.sh` keeps working; it just no longer scrapes US.
- No smoke task in the implementation plan. We've verified the multi-region path works against the live site; this change is pure filtering on top of that.

## CLI surface

The second positional arg is an **explicit set of regions to scrape**. Default is `gb-ie`.

```
./run.sh                    # 3 workers, GB+IE only            (default)
./run.sh 3                  # same, explicit workers
./run.sh 3 us               # 3 workers, US ONLY
./run.sh 3 gb-ie,us         # 3 workers, both
./run.sh 1 us               # 1 worker, US only
./run.sh 3 fr               # exits 1 with "Error: unknown region(s) fr; valid: gb-ie,us"
```

Region IDs come from `RegionTab.name`: lowercased, with `+` replaced by `-`. Today that's `gb-ie` and `us`. New tabs added to `REGION_TABS` automatically gain a region ID.

`run.sh` becomes:

```bash
#!/usr/bin/env bash
WORKERS="${1:-3}"
REGIONS="${2:-gb-ie}"
exec ./gradlew run --quiet --args="$WORKERS $REGIONS"
```

## Architecture

### `parseRegions` helper in `Main.kt`

A new top-level `fun parseRegions(args: Array<String>): Set<String>`:

```kotlin
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

`RegionTab.regionId()` is a small extension function added in `BetfairRaceListScraper.kt`:

```kotlin
internal fun RegionTab.regionId(): String = name.lowercase().replace("+", "-")
```

### `Main.main` parses both args

`main` parses workers (existing) and regions (new). Both errors caught, clean stderr message, exit 1:

```kotlin
fun main(args: Array<String>) {
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
    // ...
    val races = BetfairRaceListScraper(regions = regions).scrape()
    // ...
}
```

### `BetfairRaceListScraper` filters `REGION_TABS`

A new constructor parameter `regions: Set<String>` defaulting to "all configured regions" (so existing tests don't need updating):

```kotlin
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7",
    private val regions: Set<String> = REGION_TABS.map { it.regionId() }.toSet(),
) {
    fun scrape(): List<Race> {
        // ... unchanged setup ...
        for (region in REGION_TABS.filter { it.regionId() in regions }) {
            // ... unchanged loop body ...
        }
        // ... unchanged return ...
    }
}
```

The filter is the only change to `scrape()`. Per-region failure isolation, race assembly, sort, dedupe — all unchanged.

### Startup log gains a regions line

In `main`, after the workers line:

```kotlin
println("workers=$workerCount")
println("regions=${regions.sorted().joinToString(",")}")
```

So a default run prints `regions=gb-ie`; `./run.sh 3 gb-ie,us` prints `regions=gb-ie,us`.

## Behavior contract

| Property | Behavior |
|---|---|
| `./run.sh` (no args) | 3 workers, GB+IE only. Identical race set to today's behavior MINUS US. |
| `./run.sh N` | N workers, GB+IE only. |
| `./run.sh N <regions>` | N workers, regions = the specified set. |
| Unknown region in arg | Exit 1 with `Error: unknown region(s) <id>; valid: gb-ie,us`. No scraping. |
| Empty region string | Exit 1 with `Error: regions must be non-empty; valid: gb-ie,us`. |
| Region IDs case | Accepted in any case; `GB-IE`, `gb-ie`, `Gb-Ie` all equivalent. |
| Selecting `us` only | Only the US tab activated. GB+IE tab not clicked. Saves time on no-US-needed runs and vice versa. |
| Selecting `gb-ie` only (default) | Only the GB+IE tab activated. US tab not touched (no cookie-banner click attempt). |
| Adding a future region | Append a `RegionTab` to `REGION_TABS`. The new region's ID is auto-derived; CLI accepts it without further changes. |
| Pre-existing tests | All keep passing. `BetfairRaceListScraper()` no-arg constructor defaults to all regions, identical to today's behavior. |

## Testing

New tests in `RaceWorkerPoolTest.kt` (which already hosts `ParseWorkerCountTest` for the same reason — argument-parsing helpers in `Main.kt` are tested alongside the worker pool tests):

```kotlin
class ParseRegionsTest {
    @Test fun `defaults to gb-ie when no second arg`() {
        assertEquals(setOf("gb-ie"), parseRegions(emptyArray()))
        assertEquals(setOf("gb-ie"), parseRegions(arrayOf("3")))
    }
    @Test fun `accepts us only`() {
        assertEquals(setOf("us"), parseRegions(arrayOf("3", "us")))
    }
    @Test fun `accepts comma-separated list`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", "gb-ie,us")))
    }
    @Test fun `accepts uppercase`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", "GB-IE,US")))
    }
    @Test fun `trims whitespace around ids`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("3", " gb-ie , us ")))
    }
    @Test fun `rejects unknown region with helpful message`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseRegions(arrayOf("3", "fr"))
        }
        assertTrue("fr" in (e.message ?: ""), "message: ${e.message}")
        assertTrue("gb-ie" in (e.message ?: "") && "us" in (e.message ?: ""),
            "message must list valid ids: ${e.message}")
    }
    @Test fun `rejects empty string`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("3", "")) }
    }
    @Test fun `rejects single comma`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("3", ",")) }
    }
}
```

Existing tests remain green. The `BetfairRaceListScraper` constructor change is backwards-compatible (`regions` is defaulted), so no existing test calls need updating.

No new browser-driven test. The filter is one line; the multi-tab path itself is already verified by the previous feature's smoke run.

## Acceptance

- `./gradlew test` passes with the new `ParseRegionsTest` cases (8 new tests on top of the current 67).
- `./run.sh` runs with `regions=gb-ie` printed in the startup log; the produced `data.json` has `country` values in `{GB, IE}` only — no `US`.
- `./run.sh 3 us` runs with `regions=us` printed; produced `data.json` has `country` values in `{US}` only.
- `./run.sh 3 gb-ie,us` runs with `regions=gb-ie,us` printed; produced `data.json` has all three countries.
- `./run.sh 3 fr` exits 1 with `Error: unknown region(s) fr; valid: gb-ie,us` printed to stderr; no scraping happens.
- Validator: every produced `data.json` validates clean (no schema change).
