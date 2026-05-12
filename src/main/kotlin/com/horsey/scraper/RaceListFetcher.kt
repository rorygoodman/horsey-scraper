package com.horsey.scraper

import com.google.gson.JsonParser
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val LONDON_ZONE = ZoneId.of("Europe/London")
private val UTC_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'")

/**
 * Returns `(fromUtc, toUtc)` as ISO-8601 `Z` strings for the 24-hour day
 * that starts at midnight Europe/London on [date].
 *
 * In May (BST, UTC+1): `("2026-05-10T23:00:00Z", "2026-05-11T23:00:00Z")`.
 * In January (GMT, UTC+0): `("2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z")`.
 */
fun londonDayWindowUtc(date: LocalDate): Pair<String, String> {
    val from = date.atStartOfDay(LONDON_ZONE).toInstant()
    val to = date.plusDays(1).atStartOfDay(LONDON_ZONE).toInstant()
    return from.atZone(ZoneId.of("UTC")).format(UTC_FMT) to
           to.atZone(ZoneId.of("UTC")).format(UTC_FMT)
}

/**
 * Shreds a `listMarketCatalogue` JSON array response into `Race`s.
 * Skips entries that don't contain the fields required by [raceFromCatalogue].
 * Dedupes by `raceId` (first wins) and sorts by `(offTime, venue)`.
 */
fun parseCatalogueRaces(json: String): List<Race> {
    val arr = JsonParser.parseString(json).asJsonArray
    val out = mutableListOf<Race>()
    for (el in arr) {
        if (!el.isJsonObject) continue
        val race = raceFromCatalogue(el.asJsonObject) ?: continue
        out += race
    }
    return out.distinctBy { it.raceId }
              .sortedWith(compareBy({ it.offTime }, { it.venue }))
}

/**
 * Calls `listMarketCatalogue` once for today's WIN markets in the union of
 * [regions]' country codes, and returns the resulting `Race` list.
 */
class RaceListFetcher(private val client: BetfairClient) {
    fun fetch(regions: Set<String>, today: LocalDate = LocalDate.now(LONDON_ZONE)): List<Race> {
        val (from, to) = londonDayWindowUtc(today)
        val countries = Regions.countriesForAll(regions).sorted()
        val body = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = countries,
            from = from,
            to = to,
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val response = client.listMarketCatalogue(body)
        return parseCatalogueRaces(response)
    }
}
