package com.horsey.scraper

import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

private val HHMM = DateTimeFormatter.ofPattern("HH:mm")

/**
 * Pure formatter for the per-race `marketName` output field.
 *
 * Combines the local off time + venue (always known) with the race-type
 * snippet scraped from the page (e.g. "5f Hcap", "1m Listed"). Returns
 * `"<HH:mm> <venue> - <raceType>"` when the race-type is present, or just
 * `"<HH:mm> <venue>"` as a fallback.
 */
fun formatMarketName(race: Race, raceType: String): String {
    val time = OffsetDateTime.parse(race.offTime).format(HHMM)
    val trimmed = raceType.trim()
    return if (trimmed.isEmpty()) "$time ${race.venue}"
           else "$time ${race.venue} - $trimmed"
}

/**
 * Pure assembler: combines a [Race], a market name, and a per-market scrape
 * map into a [RaceOdds] for output. Returns null when the WIN scrape is
 * absent (per spec rule 7: race with no Win is omitted).
 */
fun assembleRaceOdds(
    race: Race,
    marketName: String,
    scrapes: Map<MarketType, MarketScrape>
): RaceOdds? {
    if (MarketType.WIN !in scrapes) return null

    val orderedTypes = MarketType.values().filter { it in scrapes }
    val marketScrapedAt = linkedMapOf<MarketType, String>()
    for (type in orderedTypes) {
        marketScrapedAt[type] = scrapes.getValue(type).scrapedAt
    }
    val runners = pivotMarketScrapes(scrapes, raceIdForWarnings = race.raceId)

    return RaceOdds(
        raceId = race.raceId,
        venue = race.venue,
        country = race.country,
        offTime = race.offTime,
        winMarketUrl = race.winMarketUrl,
        marketName = marketName,
        marketScrapedAt = marketScrapedAt,
        runners = runners
    )
}
