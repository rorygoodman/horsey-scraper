package com.horsey.scraper

private val TOP_N_REGEX = Regex("""^top ([2-5]) finish$""", RegexOption.IGNORE_CASE)

/**
 * Classifies a PLACE market by name + winners count into one of our
 * `TOP_2..TOP_5` `MarketType`s. Returns null for anything that isn't an
 * explicit Top-N Finish market (e.g. the regular "To Be Placed" market,
 * an Each Way variant, or a Top-N where the name and `numberOfWinners`
 * disagree). Mirrors the old `RelatedMarketsFinder` text filter.
 */
fun classifyTopN(name: String, numberOfWinners: Int): MarketType? {
    val match = TOP_N_REGEX.matchEntire(name.trim()) ?: return null
    val n = match.groupValues[1].toInt()
    if (n != numberOfWinners) return null
    return when (n) {
        2 -> MarketType.TOP_2
        3 -> MarketType.TOP_3
        4 -> MarketType.TOP_4
        5 -> MarketType.TOP_5
        else -> null
    }
}
