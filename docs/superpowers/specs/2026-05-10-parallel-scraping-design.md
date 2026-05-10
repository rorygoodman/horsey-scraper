---
status: draft
date: 2026-05-10
topic: Parallel race scraping with a configurable worker pool
---

# Parallel race scraping with a configurable worker pool

## Goal

Cut a full daily scrape from ~10-12 minutes to ~3-4 minutes by running multiple `BetfairRaceScraper` instances concurrently, each in its own Chrome session. The number of workers is a positional argument to `run.sh`, defaulting to 3.

## Non-goals

- No browser reuse across races within a worker. Every race still opens and closes its own Chrome (today's behavior).
- No crash recovery for dead worker threads. A thread that dies takes its current race down with it; surviving workers keep processing the queue.
- No fancy logging (per-worker log files, structured output). Plain prefixed stdout is enough.
- No change to the scrape algorithm, the `data.json` schema, the rate at which a single worker hits Betfair (still 2s between its own races), or the polling/markup conventions inside `BetfairRaceScraper`.

## CLI surface

```bash
./run.sh         # 3 workers (default)
./run.sh 1       # serial — exactly today's behavior
./run.sh 5       # 5 parallel workers
```

`run.sh` becomes:

```bash
#!/usr/bin/env bash
WORKERS="${1:-3}"
exec ./gradlew run --quiet --args="$WORKERS"
```

`Main.kt`'s `main(args: Array<String>)` parses the first positional arg with `toIntOrNull()`, defaults to 3 if absent, and validates `1..10`. Out-of-range or non-numeric input fails fast with a clear error, before any scraping starts.

```
$ ./run.sh 0
Error: workers must be between 1 and 10 (got: 0)
```

The cap of 10 is a soft guard against accidental memory blow-up — each Chrome instance is ~150-300 MB resident, so 10 workers is already ~1.5-3 GB. Easy to lift later if needed.

## Architecture

A single new file: `src/main/kotlin/com/horsey/scraper/RaceWorkerPool.kt`. One public top-level function:

```kotlin
fun scrapeRacesInParallel(
    races: List<Race>,
    workerCount: Int,
    perWorkerDelayMs: Long,
    scrapeRace: (Race) -> RaceOdds?,
    onResult: (workerId: Int, race: Race, odds: RaceOdds?) -> Unit
): List<RaceOdds>
```

- `races` — input list (already in off-time order from the race-list scraper).
- `workerCount` — number of worker threads.
- `perWorkerDelayMs` — sleep between successive races on the same worker.
- `scrapeRace` — the per-race scrape function. Production passes `{ race -> BetfairRaceScraper(race).scrape() }`; tests pass a fake.
- `onResult` — line-atomic logging hook called once per race (whether successful or not). Receives the worker id, the race, and either the `RaceOdds` or `null` (drop).

Returns successful `RaceOdds` sorted by `(offTime, venue)`.

### Internals

```
LinkedBlockingQueue<Race>  ← filled with all races up front
        │
        ▼
   ┌─────────┬─────────┬─────────┐
   │ worker0 │ worker1 │ worker2 │   N threads, each loops:
   └────┬────┴────┬────┴────┬────┘    1. race = queue.poll()
        │         │         │         2. if null → exit
        ▼         ▼         ▼         3. odds = scrapeRace(race)
ConcurrentLinkedQueue<RaceOdds>       4. onResult(id, race, odds)
        │                             5. if odds non-null → results.add
        ▼                             6. sleep(perWorkerDelayMs)
   join all → sort → return           7. goto 1
```

### Why a shared work queue (vs round-robin pre-assignment)

The user asked for "queue/round-robin." Both work; the shared queue handles uneven race times better. A 5-runner race scrapes ~5 markets in ~30s; a 24-runner field with all 5 Top-N markets can take ~50s. Round-robin pre-assignment can leave a worker idle while another grinds through its big races; a shared queue self-balances.

### Concurrency primitives

All from `java.util.concurrent` (in the JDK):

- `LinkedBlockingQueue<Race>` — thread-safe `poll()` returning `null` when empty.
- `ConcurrentLinkedQueue<RaceOdds>` — thread-safe append for results; iterated once after join.
- `Thread` — one per worker; `join()` to wait for completion.
- `AtomicInteger` for naming workers `w0`..`w<N-1>`.

No new dependencies. No coroutines (Selenium calls block threads anyway, so coroutines buy nothing here).

## Main.kt change

Replace the existing `while (queue.isNotEmpty()) { ... }` loop with one call:

```kotlin
fun main(args: Array<String>) {
    val workerCount = parseWorkerCount(args)
    // ... existing setup ...
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

    // ... existing data.json write ...
}
```

`parseWorkerCount` is a small helper in `Main.kt`. Both validation failures use `require()` so callers see one exception type, and `main` catches it to print a clean error and exit nonzero (no stack trace for user-input mistakes).

```kotlin
fun parseWorkerCount(args: Array<String>): Int {
    val raw = args.firstOrNull() ?: return 3
    val n = raw.toIntOrNull()
    require(n != null) { "workers must be between 1 and 10 (got: '$raw')" }
    require(n in 1..10) { "workers must be between 1 and 10 (got: $n)" }
    return n
}
```

In `main`:

```kotlin
val workerCount = try {
    parseWorkerCount(args)
} catch (e: IllegalArgumentException) {
    System.err.println("Error: ${e.message}")
    kotlin.system.exitProcess(1)
}
```

(`parseWorkerCount` is package-private rather than file-private so the test in `RaceWorkerPoolTest` can exercise it directly.)

`println` is line-atomic on the JVM, so interleaved log lines from different workers won't tear into each other within a line.

## Behavior contract

| Property | Behavior |
|---|---|
| Result ordering in `data.json` | Sorted by `(offTime, venue)` — identical to today (which scrapes in this order to begin with). |
| Result completeness | Identical to serial. A race that succeeds in serial still succeeds in parallel; a race that fails (drop, exception) is logged the same way. |
| Throughput | At least N×-ish speedup, modulo per-worker delay and uneven race lengths. |
| Per-worker politeness | Each worker waits `PER_RACE_DELAY_MS` (2 s) between *its own* successive scrapes. The first race on a worker has no leading delay; the last has no trailing delay. |
| Error isolation | An exception in `scrapeRace(race)` for one race does not affect any other race. The worker logs the failure via `onResult(..., null)` and pulls the next race. |
| Worker thread crash | If a worker thread itself dies (OOM, etc.), its in-flight race is lost; remaining workers keep processing. The pool join completes normally. The crash is logged to stderr by an `UncaughtExceptionHandler`. |
| `workerCount > races.size` | Surplus workers exit immediately on first empty `poll()`. Harmless. |
| `workerCount = 1` | Behaviorally identical to today's serial loop, including ordering and per-race delay. |

## Testing

A new file `src/test/kotlin/com/horsey/scraper/RaceWorkerPoolTest.kt` with these cases. The fake `scrapeRace` lambda is the test seam; no real browser is involved.

```kotlin
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
```

| Test | Assertion |
|---|---|
| `single worker scrapes all races in input order` | N=1, three races; result list size = 3, race ids in input off-time order. |
| `three workers process all races` | N=3, six races (so each worker can plausibly get >1); result list size = 6, each race id appears exactly once. |
| `result list is sorted by offTime then venue regardless of completion order` | Three races where the slowest scrape (longest fake delay) has the earliest off-time; assert sorted output ordering. |
| `slow race on one worker does not block others` | Three races, one with a 1-second `Thread.sleep` in fake scrape; with N=2 workers, total elapsed time is approximately 1s rather than ~3s. (Relaxed bound: assert < 1.5s.) |
| `null odds from scrapeRace are excluded from results but reported via onResult` | Fake returns null for one race; result list omits it; `onResult` is called for it with `odds = null`. |
| `exception in scrapeRace is caught, logged, and does not stop the pool` | Fake throws for one race; that race is omitted from results; `onResult` is called with `odds = null` for it; the other races complete. |
| `onResult is called exactly once per race` | Capture all `onResult` calls; assert one per race id, no duplicates. |
| `workerCount greater than races size completes without error` | N=5, 2 races; assert both processed. |
| `Main parseWorkerCount accepts valid range and rejects invalid input` | A separate test on the helper: `parseWorkerCount(emptyArray()) == 3`, `parseWorkerCount(arrayOf("5")) == 5`, throws on `"0"`, `"11"`, `"abc"`. |

The existing 40 tests stay green. The pool function is the only new production code that needs unit testing; everything downstream (BetfairRaceScraper, the validator) is unchanged.

A live smoke run after implementation should confirm:

- `./run.sh 1` produces the same `data.json` (modulo timestamps) as `./run.sh` did before this change.
- `./run.sh 3` produces a `data.json` that validates clean against `SchemaValidator`.
- `./run.sh 3` is roughly 3× faster than `./run.sh 1` end-to-end.

## Migration

No data migration. The `data.json` schema is unchanged. The CLI gains an optional positional argument; existing invocations (`./run.sh` with no args) keep working with a 3-worker default.

If anyone wants the literal previous behavior (serial), `./run.sh 1`.

## Acceptance

- `./run.sh` runs with 3 workers without any flags.
- `./run.sh N` for `N` in `1..10` runs with `N` workers.
- `./run.sh 0`, `./run.sh 11`, `./run.sh abc` exit with a clear error before any scraping starts.
- Output `data.json` validates clean (`SchemaValidator: VALID`).
- Output `data.json`'s `races[]` is sorted by `(offTime, venue)`.
- Live timing of `./run.sh 3` is at least 2× faster than `./run.sh 1` on a day with 15+ races.
- All 40 existing tests + the new `RaceWorkerPoolTest` cases pass.

## Open implementation questions

- **chromedriver port allocation**: each `createChromeDriver()` call lets Selenium pick a free port. Verify no collision under N=3+ — if there is, switch to explicit ports per worker. Probably fine since Selenium 4 handles this; flag if not.
- **Logging tag width**: `[w0]` vs `[w10]` makes columns ragged. Likely cosmetic; if it matters, pad to `[w%2d]`.
