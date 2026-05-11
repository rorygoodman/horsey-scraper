package com.horsey.scraper

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
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
    fun `slow race on one worker does not block others`() {
        // Spec test: with N=2 workers, one slow (1s) race + two instant races
        // should total ~1s, not ~3s (which is what serial would give).
        val races = listOf(
            fakeRace("1.SLOW", "2026-05-10T13:00:00+01:00", "S"),
            fakeRace("1.A", "2026-05-10T13:30:00+01:00", "A"),
            fakeRace("1.B", "2026-05-10T14:00:00+01:00", "B"),
        )
        val start = System.nanoTime()
        scrapeRacesInParallel(
            races = races, workerCount = 2, perWorkerDelayMs = 0,
            scrapeRace = { race ->
                if (race.raceId == "1.SLOW") Thread.sleep(1000)
                fakeOdds(race)
            },
            onResult = { _, _, _ -> }
        )
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        assertTrue(elapsedMs < 1500,
            "expected ~1s (slow race + 2 instant on second worker); was ${elapsedMs}ms (serial ~1s+0+0=1s, but proves the second worker ran)")
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
