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
    fun `parseCataloguePlaceMarkets returns a flat entry per Top-N market with eventId and marketTime`() {
        val json = """
        [
          {
            "marketId": "1.10", "marketName": "Top 2 Finish",
            "description": { "marketType": "PLACE", "numberOfWinners": 2,
                             "marketTime": "2026-05-20T12:30:00.000Z" },
            "event": { "id": "EVT1" },
            "runners": [
              { "selectionId": 100, "runnerName": "Some Horse" },
              { "selectionId": 200, "runnerName": "Outsider Bob" }
            ]
          },
          {
            "marketId": "1.11", "marketName": "To Be Placed",
            "description": { "marketType": "PLACE", "numberOfWinners": 3,
                             "marketTime": "2026-05-20T12:30:00.000Z" },
            "event": { "id": "EVT1" },
            "runners": []
          },
          {
            "marketId": "1.13", "marketName": "4 TBP",
            "description": { "marketType": "OTHER_PLACE",
                             "marketTime": "2026-05-20T12:30:00.000Z" },
            "event": { "id": "EVT1" },
            "runners": [ { "selectionId": 100, "runnerName": "Some Horse" } ]
          },
          {
            "marketId": "1.20", "marketName": "2 TBP",
            "description": { "marketType": "OTHER_PLACE",
                             "marketTime": "2026-05-20T13:00:00.000Z" },
            "event": { "id": "EVT1" },
            "runners": [ { "selectionId": 300, "runnerName": "Other Race Horse" } ]
          }
        ]
        """.trimIndent()
        val entries = parseCataloguePlaceMarkets(json)
        assertEquals(3, entries.size)
        val top2Race1 = entries.single { it.marketId == "1.10" }
        assertEquals(MarketType.TOP_2, top2Race1.type)
        assertEquals("EVT1", top2Race1.eventId)
        assertEquals("2026-05-20T12:30:00.000Z", top2Race1.marketTime)
        assertEquals(mapOf(100L to "Some Horse", 200L to "Outsider Bob"), top2Race1.runners)
        val top2Race2 = entries.single { it.marketId == "1.20" }
        assertEquals("2026-05-20T13:00:00.000Z", top2Race2.marketTime)
        assertEquals(mapOf(300L to "Other Race Horse"), top2Race2.runners)
    }

    @Test
    fun `placeMarketsByRaceId groups entries by (eventId, marketTime) so multi-race events split correctly`() {
        // Two Kempton races in the same Betfair event, each with its own TOP_2 market.
        val race1Top2 = PlaceMarketEntry(
            marketId = "1.10", type = MarketType.TOP_2,
            eventId = "EVT-KMPT", marketTime = "2026-05-20T18:00:00.000Z",
            runners = mapOf(100L to "Race1 Horse"),
        )
        val race2Top2 = PlaceMarketEntry(
            marketId = "1.20", type = MarketType.TOP_2,
            eventId = "EVT-KMPT", marketTime = "2026-05-20T18:30:00.000Z",
            runners = mapOf(200L to "Race2 Horse"),
        )
        val unmatched = PlaceMarketEntry(
            marketId = "1.99", type = MarketType.TOP_4,
            eventId = "EVT-OTHER", marketTime = "2026-05-20T19:00:00.000Z",
            runners = emptyMap(),
        )
        val raceKey = mapOf(
            "1.W1" to ("EVT-KMPT" to "2026-05-20T18:00:00.000Z"),
            "1.W2" to ("EVT-KMPT" to "2026-05-20T18:30:00.000Z"),
        )
        val grouped = placeMarketsByRaceId(listOf(race1Top2, race2Top2, unmatched), raceKey)
        assertEquals(setOf("1.W1", "1.W2"), grouped.keys)
        assertEquals(listOf("1.10"), grouped.getValue("1.W1").map { it.marketId })
        assertEquals(listOf("1.20"), grouped.getValue("1.W2").map { it.marketId })
    }

    @Test
    fun `parseWinRaceKeys returns raceId to (eventId, marketTime) from WIN catalogue`() {
        val json = """
        [
          { "marketId": "1.W1", "marketStartTime": "2026-05-20T18:00:00.000Z",
            "event": { "id": "EVT-KMPT" } },
          { "marketId": "1.W2", "marketStartTime": "2026-05-20T18:30:00.000Z",
            "event": { "id": "EVT-KMPT" } }
        ]
        """.trimIndent()
        val keys = parseWinRaceKeys(json)
        assertEquals("EVT-KMPT" to "2026-05-20T18:00:00.000Z", keys["1.W1"])
        assertEquals("EVT-KMPT" to "2026-05-20T18:30:00.000Z", keys["1.W2"])
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
            PlaceMarketEntry("1.P", MarketType.TOP_2, "EVT", "2026-05-09T12:30:00Z",
                mapOf(100L to "Some Horse"))
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
            PlaceMarketEntry("1.P", MarketType.TOP_2, "EVT", "2026-05-09T12:30:00Z",
                mapOf(100L to "Some Horse"))
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
