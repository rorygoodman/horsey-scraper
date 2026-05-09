package com.horsey.scraper

/**
 * Single-shot test of [BetfairRaceScraper] — scrapes one race URL.
 * Run with: ./gradlew run -PmainClass=com.horsey.scraper.TestRaceMainKt
 */
fun main() {
    val race = Race(
        venue = "Wexford",
        country = "IE",
        time = "19:38",
        url = "https://www.betfair.com/exchange/plus/horse-racing/market/1.257812096"
    )
    val odds = BetfairRaceScraper(race).scrape()
    println("Market: ${odds.marketName}")
    println("Runners: ${odds.horses.size}")
    odds.horses.forEach {
        println("  ${it.name.padEnd(28)}  lay=${it.layPrice}")
    }
}
