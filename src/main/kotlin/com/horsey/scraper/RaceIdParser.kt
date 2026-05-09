package com.horsey.scraper

private val RACE_ID = Regex("""\b(1\.\d+)\b""")

/**
 * Extracts a Betfair race/market ID (e.g. "1.249508314") from a market URL.
 * Returns null if no `1.<digits>` segment is found.
 */
fun extractRaceId(url: String): String? =
    RACE_ID.find(url)?.groupValues?.get(1)
