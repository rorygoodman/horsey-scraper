package com.horsey.scraper

enum class MarketType { WIN, TOP_2, TOP_3, TOP_4, TOP_5 }

/**
 * Race metadata produced by the race-list scraper. Internal type — not
 * serialised directly; its fields are flattened into [RaceOdds] for output.
 */
data class Race(
    val raceId: String,
    val venue: String,
    val country: String,    // "GB" | "IE"
    val offTime: String,    // ISO-8601 with offset
    val winMarketUrl: String
)

/**
 * Result of scraping a single market within a race. Intermediate type
 * passed from per-market scrape into the pivot. Not serialised.
 *
 * `scrapedAt` is an ISO-8601 UTC instant (e.g. "2026-05-09T12:00:04Z").
 * `runners` preserves market-page order; the second element of each
 * pair is the best lay or null if no lay is on offer.
 */
data class MarketScrape(
    val type: MarketType,
    val scrapedAt: String,
    val runners: List<Pair<String, Double?>>
)

/**
 * One runner's lay prices pivoted across markets. Key presence in `lay`
 * mirrors key presence in [RaceOdds.marketScrapedAt]: present iff the
 * market was scraped successfully.
 *
 * `selectionId` is the Betfair Exchange selection id for this runner.
 * It exists primarily so a downstream arbitrage tool can join Betfair
 * runners to PaddyPower runners (which expose the same id) without
 * horse-name normalisation. Nullable for backward compatibility with
 * older snapshots and tests that don't care about the id.
 */
data class RunnerOdds(
    val name: String,
    val lay: Map<MarketType, Double?>,
    val selectionId: Long? = null,
)

/**
 * One race's serialised output. Race fields are flattened (no nested
 * `race` object) so the JSON matches the spec example exactly.
 */
data class RaceOdds(
    val raceId: String,
    val venue: String,
    val country: String,
    val offTime: String,
    val winMarketUrl: String,
    val marketName: String,
    val marketScrapedAt: Map<MarketType, String>,
    val runners: List<RunnerOdds>
)

/**
 * Top-level wrapper for `data.json`.
 * `scrapedAt` is an ISO-8601 UTC instant for the run start.
 * `raceCount == races.size`; races with no successful WIN scrape are dropped.
 */
data class ScrapeOutput(
    val scrapedAt: String,
    val raceCount: Int,
    val races: List<RaceOdds>
)
