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
}
