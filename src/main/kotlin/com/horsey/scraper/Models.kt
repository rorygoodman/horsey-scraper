package com.horsey.scraper

enum class MarketType { WIN, TOP_2, TOP_3, TOP_4, TOP_5 }

/**
 * A horse racing meeting on the daily race list.
 *
 * @property venue Track name (e.g. "Lingfield", "Naas")
 * @property country ISO country code — "GB" or "IE"
 * @property time Off time in HH:mm (local UK time as shown on Betfair)
 * @property url Full URL to the Betfair exchange win market for this race
 */
data class Race(
    val venue: String,
    val country: String,
    val time: String,
    val url: String
)

/**
 * A single runner in a race with its current Betfair lay price.
 *
 * @property name Horse name as shown on Betfair
 * @property layPrice Best available lay price (decimal odds), or null if no lay available
 */
data class Horse(
    val name: String,
    val layPrice: Double?
)

/**
 * Result of scraping one race's Betfair win market.
 *
 * @property race Race metadata from the list page
 * @property marketName Title shown on the market page (e.g. "13:30 Lingfield - 5f Hcap")
 * @property horses Runners with their lay prices
 * @property scrapedAt ISO-8601 timestamp of the scrape
 */
data class RaceOdds(
    val race: Race,
    val marketName: String,
    val horses: List<Horse>,
    val scrapedAt: String = java.time.LocalDateTime.now().toString()
)
