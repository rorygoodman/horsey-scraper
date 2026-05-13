package com.horsey.scraper

private val UI_NAME_REGEX  = Regex("""^top ([2-5]) finish$""", RegexOption.IGNORE_CASE)
private val API_NAME_REGEX = Regex("""^([2-5]) tbp$""",        RegexOption.IGNORE_CASE)

/**
 * Classifies a market by name (+ optional winners count) into one of our
 * `TOP_2..TOP_5` `MarketType`s. Returns null for anything that isn't an
 * explicit Top-N Finish market (e.g. the regular "To Be Placed" market,
 * an Each Way variant, or a Top-N where a non-null `numberOfWinners`
 * disagrees with the N in the name).
 *
 * Two name formats are accepted: the Betfair UI text `"Top N Finish"`
 * (what the old Selenium scraper saw) and the REST API's abbreviated
 * `"N TBP"` (what `listMarketCatalogue` returns in 2026). Both formats
 * pin to `N ∈ 2..5`.
 *
 * The Betfair REST API returns `numberOfWinners = null` for these
 * markets in our projection, so the parameter is nullable. When null,
 * the name is treated as the source of truth. When non-null, it must
 * agree with the N in the name (defence-in-depth against future
 * Betfair changes).
 */
fun classifyTopN(name: String, numberOfWinners: Int?): MarketType? {
    val trimmed = name.trim()
    val match = UI_NAME_REGEX.matchEntire(trimmed)
        ?: API_NAME_REGEX.matchEntire(trimmed)
        ?: return null
    val n = match.groupValues[1].toInt()
    if (numberOfWinners != null && numberOfWinners != n) return null
    return when (n) {
        2 -> MarketType.TOP_2
        3 -> MarketType.TOP_3
        4 -> MarketType.TOP_4
        5 -> MarketType.TOP_5
        else -> null
    }
}
