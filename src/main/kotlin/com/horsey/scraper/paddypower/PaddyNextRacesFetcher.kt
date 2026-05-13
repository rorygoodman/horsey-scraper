package com.horsey.scraper.paddypower

import com.horsey.scraper.Regions
import java.time.Instant

/**
 * Pure region filter. Keeps races whose `country` is in `countries`.
 * Extracted from the fetcher so it's unit-testable without HTTP.
 */
fun filterRacesByCountries(races: List<PaddyRace>, countries: Set<String>): List<PaddyRace> =
    races.filter { it.country in countries }

/**
 * Orchestrates a one-shot PaddyPower next-races scrape:
 *   1. Calls `PaddyClient.getNextRaces()` once.
 *   2. Parses the response via [parsePaddyNextRaces].
 *   3. Filters races by the union of `regions`' country codes.
 *   4. Packages the result with a run-start `scrapedAt` timestamp.
 *
 * `nowProvider` controls the timestamps for both the top-level
 * `PaddyOutput.scrapedAt` (captured at the start of `fetch`) and each
 * race's `scrapedAt` (captured just before parsing — within a
 * sub-second of the network response).
 */
class PaddyNextRacesFetcher(
    private val client: PaddyClient,
    private val nowProvider: () -> Instant = { Instant.now() },
) {
    fun fetch(regions: Set<String>): PaddyOutput {
        val runStart = nowProvider().toString()
        val json = client.getNextRaces()
        val races = parsePaddyNextRaces(json, nowProvider)
        val filtered = filterRacesByCountries(races, Regions.countriesForAll(regions))
        return PaddyOutput(
            scrapedAt = runStart,
            raceCount = filtered.size,
            races = filtered,
        )
    }
}
