package com.horsey.scraper.arb

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ArbSchemaValidatorTest {

    private val happy = """
        {
          "computedAt": "2026-05-13T22:35:00.123Z",
          "betfairScrapedAt": "2026-05-13T22:32:52.789Z",
          "paddypowerScrapedAt": "2026-05-13T22:32:54.042Z",
          "arbCount": 1,
          "arbs": [
            {
              "venue": "Clonmel",
              "country": "IE",
              "offTime": "2026-05-14T18:50:00+01:00",
              "marketName": "18:50 Clonmel - 2m1f Hcap Hrd",
              "betfairWinMarketId": "1.258114710",
              "runner": { "name": "Champ", "selectionId": 48920004 },
              "paddypower": {
                "winPrice": 11.0, "winPriceRaw": "10/1",
                "eachWayTerms": { "fraction": 0.2, "places": 4 }
              },
              "betfair": { "winLay": 10.0, "topNLay": 2.5, "topNType": "TOP_4" },
              "margin": 0.15
            }
          ]
        }
    """.trimIndent()

    @Test fun `happy path validates`() {
        assertEquals(emptyList(), validateArbsOutput(happy))
    }

    @Test fun `arbCount mismatch is flagged`() {
        val bad = happy.replace("\"arbCount\": 1", "\"arbCount\": 5")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "arbCount" in it && "arbs.length" in it }, errs.toString())
    }

    @Test fun `non-ISO computedAt is flagged`() {
        val bad = happy.replace("2026-05-13T22:35:00.123Z", "yesterday")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "computedAt" in it && "ISO-8601" in it }, errs.toString())
    }

    @Test fun `margin of zero is flagged`() {
        val bad = happy.replace("\"margin\": 0.15", "\"margin\": 0.0")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "margin" in it }, errs.toString())
    }

    @Test fun `margin negative is flagged`() {
        val bad = happy.replace("\"margin\": 0.15", "\"margin\": -0.05")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "margin" in it }, errs.toString())
    }

    @Test fun `unknown topNType is flagged`() {
        val bad = happy.replace("\"topNType\": \"TOP_4\"", "\"topNType\": \"TOP_99\"")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "topNType" in it }, errs.toString())
    }

    @Test fun `EW fraction out of range is flagged`() {
        val bad = happy.replace("\"fraction\": 0.2", "\"fraction\": 1.5")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "fraction" in it }, errs.toString())
    }

    @Test fun `EW places out of range is flagged`() {
        val bad = happy.replace("\"places\": 4", "\"places\": 9")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "places" in it }, errs.toString())
    }

    @Test fun `missing required arb field is flagged`() {
        val bad = happy.replace("\"venue\": \"Clonmel\",", "")
        val errs = validateArbsOutput(bad)
        assertTrue(errs.any { "venue" in it }, errs.toString())
    }

    @Test fun `empty arbs array with zero arbCount validates`() {
        val empty = """
            {
              "computedAt": "2026-05-13T22:35:00Z",
              "betfairScrapedAt": "2026-05-13T22:32:52Z",
              "paddypowerScrapedAt": "2026-05-13T22:32:54Z",
              "arbCount": 0,
              "arbs": []
            }
        """.trimIndent()
        assertEquals(emptyList(), validateArbsOutput(empty))
    }
}
