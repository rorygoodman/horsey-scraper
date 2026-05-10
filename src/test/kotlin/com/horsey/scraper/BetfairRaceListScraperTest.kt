package com.horsey.scraper

import java.time.LocalDate
import java.time.ZoneId
import kotlin.test.Test
import kotlin.test.assertEquals

class BetfairRaceListScraperTest {
    private val london = ZoneId.of("Europe/London")
    private val today = LocalDate.of(2026, 5, 9)

    @Test
    fun `assembles Race objects with raceId and ISO offTime`() {
        val raw = listOf(
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        )
        val races = assembleRaces(raw, today, london)
        assertEquals(1, races.size)
        val r = races.single()
        assertEquals("1.249508314", r.raceId)
        assertEquals("Lingfield", r.venue)
        assertEquals("GB", r.country)
        assertEquals("2026-05-09T13:30:00+01:00", r.offTime)
        assertEquals("https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314", r.winMarketUrl)
    }

    @Test
    fun `skips lines for unknown venues`() {
        val raw = listOf(
            "Bogusville|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `skips lines with unparseable race id`() {
        val raw = listOf(
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `skips lines with unparseable time`() {
        val raw = listOf(
            "Lingfield|||not-a-time|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london))
    }

    @Test
    fun `dedupes by raceId and sorts by time then venue`() {
        val raw = listOf(
            "Naas|||14:00|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.222",
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111",
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
        )
        val ids = assembleRaces(raw, today, london).map { it.raceId }
        assertEquals(listOf("1.111", "1.222"), ids)
    }

    @Test
    fun `assembleRaces with countryOverride uses it for every venue`() {
        val raw = listOf(
            "Belmont Park|||18:30|||https://www.betfair.com/exchange/plus/horse-racing/market/1.555",
            "Saratoga|||19:00|||https://www.betfair.com/exchange/plus/horse-racing/market/1.556",
        )
        val races = assembleRaces(raw, today, london, countryOverride = "US")
        assertEquals(2, races.size)
        assertEquals(setOf("US"), races.map { it.country }.toSet())
    }

    @Test
    fun `assembleRaces with countryOverride still drops invalid race id`() {
        val raw = listOf(
            "Belmont Park|||18:30|||https://www.betfair.com/exchange/plus/horse-racing"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london, countryOverride = "US"))
    }

    @Test
    fun `assembleRaces with countryOverride still drops invalid time`() {
        val raw = listOf(
            "Belmont Park|||not-a-time|||https://www.betfair.com/exchange/plus/horse-racing/market/1.555"
        )
        assertEquals(emptyList(), assembleRaces(raw, today, london, countryOverride = "US"))
    }

    @Test
    fun `assembleRaces without countryOverride still uses Venues lookup (regression)`() {
        // Default countryOverride = null path. Lingfield is in Venues.UK,
        // so country should resolve to GB exactly as before this change.
        val raw = listOf(
            "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/horse-racing/market/1.111"
        )
        val races = assembleRaces(raw, today, london)
        assertEquals("GB", races.single().country)
    }
}
