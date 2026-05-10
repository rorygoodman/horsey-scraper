package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.Instant
import java.util.ArrayDeque

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
 * Entry point: a single pass over today's UK + IE Betfair Exchange races.
 *
 *   1. Reads the race list from the horse-racing landing page.
 *   2. For each race, opens one Chrome and scrapes WIN + Top 2/3/4/5 Finish.
 *   3. Pivots into per-horse lay map and writes data.json.
 *
 * Output schema: see docs/superpowers/specs/2026-05-09-multi-market-lay-schema-design.md
 */
fun main() {
    // serializeNulls is required by the spec: a `lay` map with a key whose
    // value is null means "scraped but no lay on offer." Without this,
    // Gson drops null entries and breaks key parity with marketScrapedAt.
    val gson = GsonBuilder().setPrettyPrinting().serializeNulls().create()

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
