package com.horsey.scraper.paddypower

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PaddySchemaValidatorTest {

    private val happy = """
        {
          "scrapedAt": "2026-05-13T20:30:00.123Z",
          "raceCount": 1,
          "races": [
            {
              "venue": "Punchestown",
              "country": "IE",
              "offTime": "2026-05-13T20:20:00+01:00",
              "marketName": "20:20 Punchestown - 2m INHF",
              "raceUrl": "",
              "scrapedAt": "2026-05-13T20:30:00.456Z",
              "betfairWinMarketId": "1.258114325",
              "eachWayTerms": { "fraction": 0.2, "places": 3 },
              "runners": [
                { "name": "Working Class Hero", "selectionId": 71384199, "winPrice": 5.5, "winPriceRaw": "9/2" },
                { "name": "Mister Killeens",    "selectionId": 55504985, "winPrice": null, "winPriceRaw": null }
              ]
            }
          ]
        }
    """.trimIndent()

    @Test fun `happy path validates`() {
        assertEquals(emptyList(), validatePaddyOutput(happy))
    }

    @Test fun `raceCount mismatch is flagged`() {
        val bad = happy.replace("\"raceCount\": 1", "\"raceCount\": 5")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "raceCount" in it && "races.length" in it }, errs.toString())
    }

    @Test fun `non-ISO scrapedAt is flagged`() {
        val bad = happy.replace("2026-05-13T20:30:00.123Z", "yesterday")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "scrapedAt" in it && "ISO-8601" in it }, errs.toString())
    }

    @Test fun `non-ISO offTime is flagged`() {
        val bad = happy.replace("2026-05-13T20:20:00+01:00", "20:20")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "offTime" in it }, errs.toString())
    }

    @Test fun `EW fraction out of range is flagged`() {
        val bad = happy.replace("\"fraction\": 0.2", "\"fraction\": 1.5")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "fraction" in it }, errs.toString())
    }

    @Test fun `EW places out of range is flagged`() {
        val bad = happy.replace("\"places\": 3", "\"places\": 9")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "places" in it }, errs.toString())
    }

    @Test fun `price parity violation flagged when winPrice null but raw set`() {
        val bad = happy.replace(
            "\"winPrice\": null, \"winPriceRaw\": null",
            "\"winPrice\": null, \"winPriceRaw\": \"9/2\""
        )
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "parity" in it }, errs.toString())
    }

    @Test fun `price parity violation flagged when winPrice set but raw null`() {
        val bad = happy.replace(
            "\"winPrice\": null, \"winPriceRaw\": null",
            "\"winPrice\": 5.5, \"winPriceRaw\": null"
        )
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "parity" in it }, errs.toString())
    }

    @Test fun `missing required race field flagged`() {
        val bad = happy.replace("\"venue\": \"Punchestown\",", "")
        val errs = validatePaddyOutput(bad)
        assertTrue(errs.any { "venue" in it }, errs.toString())
    }

    @Test fun `empty races array with zero raceCount validates`() {
        val empty = """
            { "scrapedAt": "2026-05-13T20:30:00Z", "raceCount": 0, "races": [] }
        """.trimIndent()
        assertEquals(emptyList(), validatePaddyOutput(empty))
    }
}
