package com.horsey.scraper

/**
 * User-facing region IDs to Betfair country codes.
 *
 * Region IDs are stable and lower-case so they round-trip as CLI args
 * (`gb-ie`, `us`). Country codes follow the Betfair API's `event.countryCode`
 * (`GB`, `IE`, `US`).
 */
object Regions {
    private val table: Map<String, Set<String>> = linkedMapOf(
        "gb-ie" to setOf("GB", "IE"),
        "us"    to setOf("US"),
    )

    val ALL: Set<String> = table.keys

    fun countriesFor(regionId: String): Set<String>? = table[regionId]

    /**
     * Union of country codes for every region in `regionIds`. Assumes ids are
     * valid (caller validates first via [countriesFor]).
     */
    fun countriesForAll(regionIds: Set<String>): Set<String> =
        regionIds.flatMap { table.getValue(it) }.toSet()
}
