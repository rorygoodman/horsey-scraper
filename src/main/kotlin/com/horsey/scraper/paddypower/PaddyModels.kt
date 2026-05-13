package com.horsey.scraper.paddypower

/**
 * Each-way terms attached to a single race. `fraction` is the place-price
 * fraction in (0, 1] (e.g. `0.2` for "1/5 odds"); `places` is the number
 * of paid places in 1..6.
 */
data class EachWayTerms(
    val fraction: Double,
    val places: Int,
)

/**
 * One runner on a PaddyPower race. `winPrice` and `winPriceRaw` are both
 * null or both populated (parity enforced by the schema validator). Null
 * means a non-runner or a price the parser could not interpret.
 *
 * `selectionId` is the same selection id Betfair uses for this horse,
 * letting an arb-finder join PaddyPower runners directly to Betfair
 * `data.json` runners without horse-name normalisation. Nullable so
 * future bookmakers without this affordance can still produce records.
 */
data class PaddyRunner(
    val name: String,
    val selectionId: Long?,
    val winPrice: Double?,
    val winPriceRaw: String?,
)

/**
 * One race as observed on PaddyPower's next-races view. `offTime` is an
 * ISO-8601 string with Europe/London offset, formatted identically to
 * the Betfair side's `offTime` so a string compare suffices as a join
 * key. `country` is ISO 3166-1 alpha-2.
 *
 * `betfairWinMarketId` is the matching Betfair Exchange WIN market id
 * (e.g. `"1.258114325"`), which PaddyPower exposes on its API. Acts as
 * the direct join key against `data.json[].raceId`. Nullable so future
 * bookmakers without this affordance can still produce records.
 */
data class PaddyRace(
    val venue: String,
    val country: String,
    val offTime: String,
    val marketName: String,
    val raceUrl: String,
    val scrapedAt: String,
    val betfairWinMarketId: String?,
    val eachWayTerms: EachWayTerms?,
    val runners: List<PaddyRunner>,
)

/** Top-level wrapper for `paddypower.json`. */
data class PaddyOutput(
    val scrapedAt: String,
    val raceCount: Int,
    val races: List<PaddyRace>,
)
