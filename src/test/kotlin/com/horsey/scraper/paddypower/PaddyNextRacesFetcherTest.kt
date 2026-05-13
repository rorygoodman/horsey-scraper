package com.horsey.scraper.paddypower

import com.horsey.scraper.Regions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PaddyNextRacesFetcherTest {

    @Test
    fun `region filter keeps races whose country is in the union`() {
        val races = listOf(
            race("Lingfield", "GB"),
            race("Naas", "IE"),
            race("Belmont", "US"),
        )
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        val filtered = filterRacesByCountries(races, countries)
        assertEquals(listOf("Lingfield", "Naas"), filtered.map { it.venue })
    }

    @Test
    fun `region filter drops races whose country is outside the union`() {
        val races = listOf(race("Belmont", "US"), race("Sha Tin", "HK"))
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        assertTrue(filterRacesByCountries(races, countries).isEmpty())
    }

    @Test
    fun `region filter selecting both gb-ie and us keeps all three`() {
        val races = listOf(race("Lingfield", "GB"), race("Naas", "IE"), race("Belmont", "US"))
        val countries = Regions.countriesForAll(setOf("gb-ie", "us"))
        assertEquals(3, filterRacesByCountries(races, countries).size)
    }

    @Test
    fun `empty input gives empty output`() {
        val countries = Regions.countriesForAll(setOf("gb-ie"))
        assertTrue(filterRacesByCountries(emptyList(), countries).isEmpty())
    }

    private fun race(venue: String, country: String) = PaddyRace(
        venue = venue, country = country,
        offTime = "2026-05-13T20:00:00+01:00",
        marketName = "20:00 $venue",
        raceUrl = "",
        scrapedAt = "2026-05-13T19:00:00Z",
        betfairWinMarketId = null,
        eachWayTerms = null,
        runners = listOf(PaddyRunner("Some Horse", selectionId = null, winPrice = 5.5, winPriceRaw = "9/2")),
    )
}
