package com.horsey.scraper

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals

class ModelsJsonTest {
    private val gson = Gson()

    @Test
    fun `RaceOdds serializes with flat race fields and pivoted runners`() {
        val odds = RaceOdds(
            raceId = "1.249508314",
            venue = "Lingfield",
            country = "GB",
            offTime = "2026-05-09T13:30:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
            marketName = "13:30 Lingfield - 5f Hcap",
            marketScrapedAt = linkedMapOf(
                MarketType.WIN to "2026-05-09T12:00:04Z",
                MarketType.TOP_3 to "2026-05-09T12:00:11Z"
            ),
            runners = listOf(
                RunnerOdds(
                    name = "Some Horse",
                    lay = linkedMapOf(MarketType.WIN to 4.8, MarketType.TOP_3 to 1.7)
                )
            )
        )

        val expected = """
            {
              "raceId": "1.249508314",
              "venue": "Lingfield",
              "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z", "TOP_3": "2026-05-09T12:00:11Z" },
              "runners": [
                { "name": "Some Horse", "lay": { "WIN": 4.8, "TOP_3": 1.7 } }
              ]
            }
        """.trimIndent()

        assertEquals(JsonParser.parseString(expected), JsonParser.parseString(gson.toJson(odds)))
    }

    @Test
    fun `ScrapeOutput serializes with scrapedAt, raceCount, races`() {
        val output = ScrapeOutput(
            scrapedAt = "2026-05-09T12:00:00Z",
            raceCount = 0,
            races = emptyList()
        )
        val expected = """{"scrapedAt":"2026-05-09T12:00:00Z","raceCount":0,"races":[]}"""
        assertEquals(JsonParser.parseString(expected), JsonParser.parseString(gson.toJson(output)))
    }

    @Test
    fun `serializeNulls is required to preserve null lay entries (key parity)`() {
        // Spec rule: a runner's `lay` map must have the same keys as the
        // race's `marketScrapedAt`. A null value means "scraped, no lay on
        // offer" — but Gson drops nulls by default, which would silently
        // break key parity. Main.kt must use GsonBuilder().serializeNulls().
        val odds = RaceOdds(
            raceId = "1.111", venue = "Lingfield", country = "GB",
            offTime = "2026-05-09T13:30:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.111",
            marketName = "x",
            marketScrapedAt = linkedMapOf(MarketType.WIN to "2026-05-09T12:00:00Z"),
            runners = listOf(
                RunnerOdds(name = "X", lay = linkedMapOf(MarketType.WIN to null))
            )
        )

        val withNulls = GsonBuilder().serializeNulls().create().toJson(odds)
        assertEquals(
            JsonParser.parseString("""{"WIN":null}"""),
            JsonParser.parseString(withNulls).asJsonObject.get("runners").asJsonArray[0].asJsonObject.get("lay")
        )
    }
}
