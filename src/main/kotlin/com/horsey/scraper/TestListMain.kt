package com.horsey.scraper

/**
 * Single-shot test of [BetfairRaceListScraper] — prints the parsed race list.
 * Run with: ./gradlew run -PmainClass=com.horsey.scraper.TestListMainKt
 */
fun main() {
    val races = BetfairRaceListScraper().scrape()
    println("Found ${races.size} GB/IE races")
    races.forEach { println("  ${it.time}  ${it.country}  ${it.venue.padEnd(15)}  ${it.url}") }
}
