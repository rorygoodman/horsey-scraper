package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class BetfairRaceScraperAssemblyTest {
    private val race = Race(
        raceId = "1.111", venue = "Lingfield", country = "GB",
        offTime = "2026-05-09T13:30:00+01:00",
        winMarketUrl = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111"
    )

    @Test
    fun `assembleRaceOdds produces flat fields and pivot`() {
        val scrapes = mapOf(
            MarketType.WIN to MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
                listOf("X" to 3.0)),
            MarketType.TOP_3 to MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
                listOf("X" to 1.5))
        )
        val odds = assembleRaceOdds(race, "13:30 Lingfield - 5f Hcap", scrapes)
        assertEquals(race.raceId, odds!!.raceId)
        assertEquals("Lingfield", odds.venue)
        assertEquals("GB", odds.country)
        assertEquals(race.offTime, odds.offTime)
        assertEquals(race.winMarketUrl, odds.winMarketUrl)
        assertEquals("13:30 Lingfield - 5f Hcap", odds.marketName)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), odds.marketScrapedAt.keys)
        assertEquals(1, odds.runners.size)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), odds.runners[0].lay.keys)
    }

    @Test
    fun `assembleRaceOdds returns null when WIN scrape is missing`() {
        val scrapes = mapOf(
            MarketType.TOP_3 to MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
                listOf("X" to 1.5))
        )
        assertNull(assembleRaceOdds(race, "irrelevant", scrapes))
    }

    @Test
    fun `formatMarketName combines time + venue + race type`() {
        assertEquals("13:30 Lingfield - 5f Hcap", formatMarketName(race, "5f Hcap"))
    }

    @Test
    fun `formatMarketName trims whitespace from race type`() {
        assertEquals("13:30 Lingfield - 1m Listed",
            formatMarketName(race, "  1m Listed\n"))
    }

    @Test
    fun `formatMarketName falls back to time + venue when race type empty or blank`() {
        assertEquals("13:30 Lingfield", formatMarketName(race, ""))
        assertEquals("13:30 Lingfield", formatMarketName(race, "   "))
    }

    @Test
    fun `formatMarketName uses local time of offTime, not UTC`() {
        // 14:30 BST should render as "14:30", not "13:30" (the UTC equivalent).
        val bstRace = race.copy(
            venue = "Naas",
            offTime = "2026-05-10T14:30:00+01:00"
        )
        assertEquals("14:30 Naas - 1m4f Mdn", formatMarketName(bstRace, "1m4f Mdn"))
    }

    @Test
    fun `marketScrapedAt preserves MarketType declared order`() {
        val scrapes = mapOf(
            MarketType.TOP_5 to MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z",
                listOf("X" to 1.1)),
            MarketType.WIN to MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
                listOf("X" to 3.0)),
            MarketType.TOP_2 to MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z",
                listOf("X" to 2.0))
        )
        val odds = assembleRaceOdds(race, "x", scrapes)
        assertEquals(listOf(MarketType.WIN, MarketType.TOP_2, MarketType.TOP_5),
            odds!!.marketScrapedAt.keys.toList())
    }
}
