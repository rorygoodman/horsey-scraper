package com.horsey.scraper

import com.google.gson.GsonBuilder
import java.io.File
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.ArrayDeque

/** Polite delay between scraping individual races. */
private const val PER_RACE_DELAY_MS = 2_000L

/** Output file written after the run completes. */
private const val OUTPUT_FILE = "data.json"

/**
 * Entry point: a single pass over today's UK + IE Betfair Exchange races.
 *
 *   1. Reads the race list from the horse-racing landing page.
 *   2. Walks through each race sequentially, one browser at a time.
 *   3. Writes a data.json snapshot of horses + lay prices and exits.
 */
fun main() {
    val gson = GsonBuilder().setPrettyPrinting().create()

    println("Horsey Scraper — Betfair Exchange (UK + IE)")
    println("=".repeat(80))

    val started = ZonedDateTime.now()
        .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss z"))

    println("\n[$started] Fetching today's race list…")
    val races = BetfairRaceListScraper().scrape()
    println("Found ${races.size} UK/IE races today.")
    races.forEach { println("  ${it.time}  ${it.country}  ${it.venue}") }

    val results = mutableListOf<RaceOdds>()
    if (races.isNotEmpty()) {
        val queue = ArrayDeque(races)
        while (queue.isNotEmpty()) {
            val race = queue.poll()
            print("Scraping ${race.time} ${race.venue}… ")
            try {
                val odds = BetfairRaceScraper(race).scrape()
                val priced = odds.horses.count { it.layPrice != null }
                println("${odds.horses.size} runners ($priced with lay)")
                results.add(odds)
            } catch (e: Exception) {
                println("FAILED: ${e.message}")
            }
            if (queue.isNotEmpty()) Thread.sleep(PER_RACE_DELAY_MS)
        }
    }

    val payload = mapOf(
        "timestamp" to started,
        "raceCount" to results.size,
        "races" to results
    )
    File(OUTPUT_FILE).writeText(gson.toJson(payload))
    println("\nWrote $OUTPUT_FILE (${results.size} races)")
}
