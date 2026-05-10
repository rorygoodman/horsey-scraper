package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SchemaValidatorTest {
    private val goodJson = """
    {
      "scrapedAt": "2026-05-09T12:00:00Z",
      "raceCount": 1,
      "races": [
        {
          "raceId": "1.249508314",
          "venue": "Lingfield",
          "country": "GB",
          "offTime": "2026-05-09T13:30:00+01:00",
          "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
          "marketName": "13:30 Lingfield - 5f Hcap",
          "marketScrapedAt": {
            "WIN": "2026-05-09T12:00:04Z", "TOP_2": "2026-05-09T12:00:08Z",
            "TOP_3": "2026-05-09T12:00:11Z", "TOP_4": "2026-05-09T12:00:14Z",
            "TOP_5": "2026-05-09T12:00:17Z"
          },
          "runners": [
            { "name": "Some Horse",
              "lay": { "WIN": 4.8, "TOP_2": 2.5, "TOP_3": 1.7, "TOP_4": 1.4, "TOP_5": 1.2 } }
          ]
        }
      ]
    }
    """.trimIndent()

    @Test
    fun `valid full file produces no errors`() {
        assertEquals(emptyList(), validateScrapeOutput(goodJson))
    }

    @Test
    fun `partial markets pass when key parity holds`() {
        val partial = """
        {
          "scrapedAt": "2026-05-09T12:00:00Z",
          "raceCount": 1,
          "races": [
            {
              "raceId": "1.249508314",
              "venue": "Lingfield", "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z", "TOP_3": "2026-05-09T12:00:11Z" },
              "runners": [ { "name": "X", "lay": { "WIN": 4.8, "TOP_3": 1.7 } } ]
            }
          ]
        }
        """.trimIndent()
        assertEquals(emptyList(), validateScrapeOutput(partial))
    }

    @Test
    fun `key parity violation is flagged`() {
        // marketScrapedAt has WIN only, but runner's lay has WIN + TOP_3.
        val bad = """
        {
          "scrapedAt": "2026-05-09T12:00:00Z",
          "raceCount": 1,
          "races": [
            {
              "raceId": "1.249508314",
              "venue": "Lingfield", "country": "GB",
              "offTime": "2026-05-09T13:30:00+01:00",
              "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
              "marketName": "13:30 Lingfield - 5f Hcap",
              "marketScrapedAt": { "WIN": "2026-05-09T12:00:04Z" },
              "runners": [ { "name": "X", "lay": { "WIN": 4.8, "TOP_3": 1.7 } } ]
            }
          ]
        }
        """.trimIndent()
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("key parity") },
            "errors were: $errors")
    }

    @Test
    fun `bad raceId regex is flagged`() {
        val bad = goodJson.replace(""""raceId": "1.249508314"""", """"raceId": "X.123"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("raceId") }, "errors were: $errors")
    }

    @Test
    fun `bad scrapedAt format is flagged`() {
        val bad = goodJson.replace(""""scrapedAt": "2026-05-09T12:00:00Z"""",
            """"scrapedAt": "yesterday"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("scrapedAt") }, "errors were: $errors")
    }

    @Test
    fun `bad country is flagged`() {
        val bad = goodJson.replace(""""country": "GB"""", """"country": "FR"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("country") }, "errors were: $errors")
    }

    @Test
    fun `bad offTime format is flagged`() {
        val bad = goodJson.replace(
            """"offTime": "2026-05-09T13:30:00+01:00"""",
            """"offTime": "13:30"""")
        val errors = validateScrapeOutput(bad)
        assertTrue(errors.any { it.contains("offTime") }, "errors were: $errors")
    }

    @Test
    fun `accepts country US`() {
        val good = goodJson.replace(""""country": "GB"""", """"country": "US"""")
        assertEquals(emptyList(), validateScrapeOutput(good))
    }
}
