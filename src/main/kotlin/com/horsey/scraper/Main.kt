package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.Instant

private const val PER_RACE_DELAY_MS = 2_000L
private const val OUTPUT_FILE = "data.json"

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
    println("Found ${races.size} races today.")
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
