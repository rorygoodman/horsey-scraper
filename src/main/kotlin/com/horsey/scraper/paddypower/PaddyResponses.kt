package com.horsey.scraper.paddypower

private val FRACTION_REGEX = Regex("""^(\d+)/(\d+)$""")
private val EVENS_FORMS = setOf("evens", "evs", "even")

/**
 * Converts a PaddyPower price string into decimal odds.
 *
 * Accepts simple integer fractions (`"5/2"` → `3.5`) and the "evens"
 * word forms (`"evens"`, `"EVS"`, `"Evens"` → `2.0`). Returns null for
 * `"SP"`, empty strings, whitespace-only, divide-by-zero, negatives,
 * non-integer fractions, or anything else that isn't a recognised
 * fractional odds string.
 *
 * Decimal odds = 1 + numerator/denominator.
 *
 * Kept as a utility for future bookmakers whose APIs only return
 * fractional strings. PaddyPower's `content-managed-page` endpoint
 * provides decimal odds directly, so this function is not used on the
 * PP scrape path; it's available for re-use.
 */
fun fractionalToDecimal(raw: String): Double? {
    val s = raw.trim()
    if (s.isEmpty()) return null
    if (s.lowercase() in EVENS_FORMS) return 2.0
    val m = FRACTION_REGEX.matchEntire(s) ?: return null
    val num = m.groupValues[1].toInt()
    val den = m.groupValues[2].toInt()
    if (den == 0) return null
    return 1.0 + num.toDouble() / den.toDouble()
}
