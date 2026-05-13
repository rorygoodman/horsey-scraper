package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RaceOddsFetcherTest {
    @Test
    fun `chunkOf40 chunks lists into groups of 40`() {
        assertEquals(emptyList(), chunkOf40(emptyList<Int>()))
        assertEquals(listOf((1..40).toList()), chunkOf40((1..40).toList()))
        val ninety = (1..90).toList()
        val chunks = chunkOf40(ninety)
        assertEquals(3, chunks.size)
        assertEquals(40, chunks[0].size)
        assertEquals(40, chunks[1].size)
        assertEquals(10, chunks[2].size)
    }

    @Test
    fun `parseCataloguePlaceMarkets classifies and joins to eventId`() {
        val json = """
        [
          {
            "marketId": "1.10", "marketName": "Top 2 Finish",
            "description": { "marketType": "PLACE", "numberOfWinners": 2 },
            "event": { "id": "EVT1" },
            "runners": [
              { "selectionId": 100, "runnerName": "Some Horse" },
              { "selectionId": 200, "runnerName": "Outsider Bob" }
            ]
          },
          {
            "marketId": "1.11", "marketName": "To Be Placed",
            "description": { "marketType": "PLACE", "numberOfWinners": 3 },
            "event": { "id": "EVT1" },
            "runners": []
          },
          {
            "marketId": "1.12", "marketName": "Top 3 Finish",
            "description": { "marketType": "PLACE", "numberOfWinners": 3 },
            "event": { "id": "EVT1" },
            "runners": [ { "selectionId": 100, "runnerName": "Some Horse" } ]
          },
          {
            "marketId": "1.13", "marketName": "4 TBP",
            "description": { "marketType": "OTHER_PLACE" },
            "event": { "id": "EVT1" },
            "runners": [ { "selectionId": 100, "runnerName": "Some Horse" } ]
          }
        ]
        """.trimIndent()
        val byEvent = parseCataloguePlaceMarkets(json)
        assertEquals(setOf("EVT1"), byEvent.keys)
        val markets = byEvent.getValue("EVT1").associateBy { it.type }
        assertEquals(setOf(MarketType.TOP_2, MarketType.TOP_3, MarketType.TOP_4), markets.keys)
        assertEquals("1.10", markets.getValue(MarketType.TOP_2).marketId)
        assertEquals("1.13", markets.getValue(MarketType.TOP_4).marketId)
        assertEquals(mapOf(100L to "Some Horse", 200L to "Outsider Bob"),
            markets.getValue(MarketType.TOP_2).runners)
    }

    @Test
    fun `parseWinCatalogueRunners returns selectionId-ordered runner names per marketId`() {
        val json = """
        [
          {
            "marketId": "1.1", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "EVT1", "countryCode": "GB", "venue": "Lingfield" },
            "runners": [
              { "selectionId": 100, "runnerName": "Some Horse", "sortPriority": 1 },
              { "selectionId": 200, "runnerName": "Outsider Bob", "sortPriority": 2 }
            ]
          }
        ]
        """.trimIndent()
        val byMarket = parseWinCatalogueRunners(json)
        val runners = byMarket.getValue("1.1")
        assertEquals(listOf(100L to "Some Horse", 200L to "Outsider Bob"), runners)
    }

    @Test
    fun `parseBookSnapshots produces a snapshot per marketId`() {
        val json = """
        [
          { "marketId": "1.1", "status": "OPEN",
            "runners": [ { "selectionId": 100, "ex": { "availableToLay": [{ "price": 4.8 }] } } ] },
          { "marketId": "1.2", "status": "SUSPENDED", "runners": [] }
        ]
        """.trimIndent()
        val snaps = parseBookSnapshots(json)
        assertEquals(MarketBookStatus.OPEN, snaps.getValue("1.1").status)
        assertEquals(4.8, snaps.getValue("1.1").layBySelectionId[100L])
        assertEquals(MarketBookStatus.OTHER, snaps.getValue("1.2").status)
    }

    @Test
    fun `joinScrapes drops races whose WIN is OTHER`() {
        val race = race("1.W", "Lingfield")
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = emptyMap(),
            snapshots = mapOf("1.W" to MarketBookSnapshot(MarketBookStatus.OTHER, emptyMap())),
            winRunners = mapOf("1.W" to emptyList()),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertTrue(out.isEmpty())
    }

    @Test
    fun `joinScrapes builds a RaceOdds with WIN-only when no PLACE markets present`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(
            MarketBookStatus.OPEN,
            mapOf(100L to 4.8, 200L to null),
        )
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = emptyMap(),
            snapshots = mapOf("1.W" to winSnap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse", 200L to "Outsider Bob")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertEquals(1, out.size)
        val odds = out[0]
        assertEquals(setOf(MarketType.WIN), odds.marketScrapedAt.keys)
        assertEquals("2026-05-09T12:00:00Z", odds.marketScrapedAt[MarketType.WIN])
        assertEquals(listOf("Some Horse", "Outsider Bob"), odds.runners.map { it.name })
        assertEquals(mapOf(MarketType.WIN to 4.8), odds.runners[0].lay)
    }

    @Test
    fun `joinScrapes pivots WIN plus a successful TOP_2`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 4.8))
        val top2Snap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 2.5))
        val placeMarkets = mapOf("1.W" to listOf(
            PlaceMarketEntry("1.P", MarketType.TOP_2, mapOf(100L to "Some Horse"))
        ))
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = placeMarkets,
            snapshots = mapOf("1.W" to winSnap, "1.P" to top2Snap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        assertEquals(1, out.size)
        val odds = out[0]
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_2), odds.marketScrapedAt.keys)
        assertEquals(mapOf(MarketType.WIN to 4.8, MarketType.TOP_2 to 2.5), odds.runners[0].lay)
    }

    @Test
    fun `joinScrapes drops a TOP_N where the book is OTHER`() {
        val race = race("1.W", "Lingfield")
        val winSnap = MarketBookSnapshot(MarketBookStatus.OPEN, mapOf(100L to 4.8))
        val top2Snap = MarketBookSnapshot(MarketBookStatus.OTHER, emptyMap())
        val placeMarkets = mapOf("1.W" to listOf(
            PlaceMarketEntry("1.P", MarketType.TOP_2, mapOf(100L to "Some Horse"))
        ))
        val out = joinScrapes(
            races = listOf(race),
            placeMarketsByRaceId = placeMarkets,
            snapshots = mapOf("1.W" to winSnap, "1.P" to top2Snap),
            winRunners = mapOf("1.W" to listOf(100L to "Some Horse")),
            winMarketName = "13:30 Lingfield",
            scrapedAt = "2026-05-09T12:00:00Z",
        )
        val odds = out.single()
        assertEquals(setOf(MarketType.WIN), odds.marketScrapedAt.keys)
        assertNull(odds.runners[0].lay[MarketType.TOP_2])
    }

    private fun race(raceId: String, venue: String) =
        Race(
            raceId = raceId,
            venue = venue,
            country = "GB",
            offTime = "2026-05-09T13:30:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$raceId",
        )
}
