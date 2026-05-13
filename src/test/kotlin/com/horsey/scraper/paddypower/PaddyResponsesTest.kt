package com.horsey.scraper.paddypower

import java.nio.file.Files
import java.nio.file.Paths
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Tests for `parsePaddyNextRaces`.
 *
 * The PaddyPower next-races JSON shape (captured 2026-05-13 from
 * `apisms.paddypower.com/smspp/content-managed-page/v7`) is:
 *   {
 *     "layout":      { ... cards listing raceIds ... },
 *     "attachments": {
 *       "races":   { "<raceId>": { raceId, winMarketId, winMarketName,
 *                                  startTime, countryCode, venue, ... } },
 *       "markets": { "<marketId>": { marketId, raceId, marketType,
 *                                    exchangeMarketId, runners[...],
 *                                    numberOfPlaces,
 *                                    placeFraction:{numerator,denominator},
 *                                    eachwayAvailable } }
 *     }
 *   }
 *
 * Races and markets are joined by `race.winMarketId == market.marketId`.
 * Each runner carries `selectionId`, `runnerName`, `runnerStatus`,
 * and prices in `winRunnerOdds.trueOdds.{decimalOdds.decimalOdds,
 * fractionalOdds:{numerator,denominator}}`.
 */
class PaddyResponsesTest {

    private val fixedNow = Instant.parse("2026-05-13T12:00:00Z")
    private val nowProvider = { fixedNow }

    @Test
    fun `parses the real fixture into at least one race`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        assertTrue(races.isNotEmpty(), "fixture should contain at least one race")
        val first = races.first()
        assertTrue(first.venue.isNotBlank())
        assertTrue(first.country.isNotBlank())
        assertTrue(
            first.offTime.matches(Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)""")),
            "offTime must be ISO-8601 with offset, got '${first.offTime}'",
        )
        assertEquals(fixedNow.toString(), first.scrapedAt)
        assertTrue(first.runners.isNotEmpty(), "race must have at least one runner")
    }

    @Test
    fun `synthetic runners are filtered out`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val allNames = races.flatMap { it.runners.map { r -> r.name } }
        assertTrue(allNames.isNotEmpty())
        for (synthetic in listOf("Unnamed Favourite", "Unnamed 2nd Favourite", "The Field")) {
            assertTrue(synthetic !in allNames, "found synthetic runner '$synthetic' in output")
        }
    }

    @Test
    fun `marketName is HH_mm Venue - race-type`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        // Salisbury market is 16:40 UTC = 17:40 BST in May → "17:40 Salisbury - 6f Hcap"
        assertEquals("17:40 Salisbury - 6f Hcap", race.marketName)
    }

    @Test
    fun `betfairWinMarketId is captured from market exchangeMarketId`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        assertEquals("1.258114325", race.betfairWinMarketId)
    }

    @Test
    fun `selectionId is captured on each runner`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        val stoleMyHeart = race.runners.first { it.name == "Stole My Heart" }
        assertEquals(28252276L, stoleMyHeart.selectionId)
    }

    @Test
    fun `decimal and fractional prices are both populated`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        val r = race.runners.first { it.name == "Stole My Heart" }
        // fixture has decimalOdds=21, fractionalOdds 20/1
        assertEquals(21.0, r.winPrice)
        assertEquals("20/1", r.winPriceRaw)
    }

    @Test
    fun `each-way terms come from numberOfPlaces and placeFraction`() {
        val json = Files.readString(Paths.get("src/test/resources/paddy-next-races-sample.json"))
        val races = parsePaddyNextRaces(json, nowProvider)
        val race = races.first { it.venue == "Salisbury" }
        // fixture: numberOfPlaces=4, placeFraction 1/5
        assertEquals(EachWayTerms(0.2, 4), race.eachWayTerms)
    }

    @Test
    fun `race without country code is dropped`() {
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "venue": "Nowhere" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN", "runners": [],
                                     "exchangeMarketId": "1.x" } } } }
        """.trimIndent()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `race with zero real runners is dropped`() {
        // All runners are synthetic placeholders → effectively empty.
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN",
                                     "exchangeMarketId": "1.x",
                                     "numberOfPlaces": 3,
                                     "placeFraction": {"numerator":1,"denominator":5},
                                     "eachwayAvailable": true,
                                     "runners": [
                                       { "selectionId": 10518227, "runnerName": "Unnamed Favourite", "runnerStatus": "ACTIVE" },
                                       { "selectionId": 327679,   "runnerName": "The Field",         "runnerStatus": "REMOVED" }
                                     ] } } } }
        """.trimIndent()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `runner with REMOVED status keeps both price fields null`() {
        // Construct a race with one normal runner + one withdrawn real horse.
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN",
                                     "exchangeMarketId": "1.x",
                                     "numberOfPlaces": 3,
                                     "placeFraction": {"numerator":1,"denominator":5},
                                     "eachwayAvailable": true,
                                     "runners": [
                                       { "selectionId": 1001, "runnerName": "Real Horse", "runnerStatus": "ACTIVE",
                                         "winRunnerOdds": { "trueOdds": { "decimalOdds": {"decimalOdds":5.0},
                                                                          "fractionalOdds": {"numerator":4,"denominator":1} } } },
                                       { "selectionId": 1002, "runnerName": "Withdrawn Horse", "runnerStatus": "REMOVED" }
                                     ] } } } }
        """.trimIndent()
        val race = parsePaddyNextRaces(json, nowProvider).single()
        val withdrawn = race.runners.first { it.name == "Withdrawn Horse" }
        assertNull(withdrawn.winPrice)
        assertNull(withdrawn.winPriceRaw)
        assertNotNull(race.runners.firstOrNull { it.name == "Real Horse" })
    }

    @Test
    fun `race whose winMarketId has no entry in markets is dropped`() {
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m-missing",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { } } }
        """.trimIndent()
        assertTrue(parsePaddyNextRaces(json, nowProvider).isEmpty())
    }

    @Test
    fun `partial price data drops both fields to enforce parity`() {
        // decimalOdds present but fractionalOdds missing numerator → both nulled.
        val json = """
            { "attachments": {
                "races": { "1.1": { "raceId": "1.1", "winMarketId": "m1",
                                    "winMarketName": "5f Hcap",
                                    "startTime": "2026-05-13T19:00:00.000Z",
                                    "countryCode": "GB", "venue": "Bath" } },
                "markets": { "m1": { "marketId": "m1", "raceId": "1.1",
                                     "marketType": "WIN",
                                     "exchangeMarketId": "1.x",
                                     "numberOfPlaces": 3,
                                     "placeFraction": {"numerator":1,"denominator":5},
                                     "eachwayAvailable": true,
                                     "runners": [
                                       { "selectionId": 1001, "runnerName": "Partial Horse", "runnerStatus": "ACTIVE",
                                         "winRunnerOdds": { "trueOdds": { "decimalOdds": {"decimalOdds":5.0},
                                                                          "fractionalOdds": {"denominator":1} } } }
                                     ] } } } }
        """.trimIndent()
        val r = parsePaddyNextRaces(json, nowProvider).single().runners.single()
        assertNull(r.winPrice)
        assertNull(r.winPriceRaw)
    }
}
