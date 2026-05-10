package com.horsey.scraper

import com.google.gson.GsonBuilder

/**
 * Single-shot test of [BetfairRaceScraper] — scrapes one race URL.
 * Run with:
 *   ./gradlew run -PmainClass=com.horsey.scraper.TestRaceMainKt --args='<win-market-url>'
 */
fun main(args: Array<String>) {
    val url = args.firstOrNull() ?: error("Pass a Win market URL as the first argument")
    val raceId = extractRaceId(url) ?: error("URL has no parseable race ID: $url")
    val race = Race(
        raceId = raceId,
        venue = "Unknown",
        country = "??",
        offTime = "1970-01-01T00:00:00Z",
        winMarketUrl = url
    )
    val odds = BetfairRaceScraper(race).scrape()
    if (odds == null) {
        println("Scrape returned null (no WIN data)")
        return
    }
    println(GsonBuilder().setPrettyPrinting().create().toJson(odds))
}
