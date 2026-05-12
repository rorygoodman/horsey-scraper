package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BetfairResponsesTest {
    // --- parseSsoid ---
    @Test
    fun `parseSsoid extracts token on SUCCESS`() {
        val json = """{ "token": "abc123", "status": "SUCCESS", "error": "" }"""
        assertEquals("abc123", parseSsoid(json))
    }

    @Test
    fun `parseSsoid throws on non-SUCCESS with status in message`() {
        val json = """{ "token": "", "status": "LOGIN_RESTRICTED", "error": "" }"""
        val e = assertFailsWith<IllegalStateException> { parseSsoid(json) }
        assertTrue("LOGIN_RESTRICTED" in (e.message ?: ""), e.message)
    }

    @Test
    fun `parseSsoid mentions 2FA hint on LOGIN_RESTRICTED`() {
        val json = """{ "token": "", "status": "LOGIN_RESTRICTED", "error": "" }"""
        val e = assertFailsWith<IllegalStateException> { parseSsoid(json) }
        assertTrue("2FA" in (e.message ?: ""), "expected 2FA hint: ${e.message}")
    }

    @Test
    fun `parseSsoid throws on malformed JSON`() {
        assertFailsWith<IllegalStateException> { parseSsoid("not json") }
    }

    @Test
    fun `parseSsoid throws IllegalStateException when token is null on SUCCESS`() {
        val json = """{ "token": null, "status": "SUCCESS" }"""
        assertFailsWith<IllegalStateException> { parseSsoid(json) }
    }

    @Test
    fun `parseSsoid throws IllegalStateException when token field is absent on SUCCESS`() {
        val json = """{ "status": "SUCCESS" }"""
        assertFailsWith<IllegalStateException> { parseSsoid(json) }
    }

    // --- raceFromCatalogue ---
    @Test
    fun `raceFromCatalogue builds Race from a WIN market entry`() {
        val json = """
        {
          "marketId": "1.249508314",
          "marketName": "5f Hcap",
          "marketStartTime": "2026-05-09T12:30:00.000Z",
          "description": { "marketType": "WIN", "numberOfWinners": 1 },
          "event": { "id": "32189123", "countryCode": "GB", "venue": "Lingfield" }
        }
        """.trimIndent()
        val race = raceFromCatalogue(json)
        assertEquals("1.249508314", race!!.raceId)
        assertEquals("Lingfield", race.venue)
        assertEquals("GB", race.country)
        assertEquals("2026-05-09T13:30:00+01:00", race.offTime)
        assertEquals(
            "https://www.betfair.com/exchange/plus/horse-racing/market/1.249508314",
            race.winMarketUrl
        )
    }

    @Test
    fun `raceFromCatalogue handles winter UTC offset`() {
        val json = """
        {
          "marketId": "1.1",
          "marketName": "Mdn",
          "marketStartTime": "2026-01-15T14:30:00.000Z",
          "description": { "marketType": "WIN", "numberOfWinners": 1 },
          "event": { "id": "1", "countryCode": "GB", "venue": "Lingfield" }
        }
        """.trimIndent()
        val race = raceFromCatalogue(json)
        assertEquals("2026-01-15T14:30:00Z", race!!.offTime)
    }

    @Test
    fun `raceFromCatalogue returns null when required fields missing`() {
        val noVenue = """
        {
          "marketId": "1.1",
          "marketStartTime": "2026-05-09T12:30:00.000Z",
          "description": { "marketType": "WIN" },
          "event": { "id": "1", "countryCode": "GB" }
        }
        """.trimIndent()
        assertNull(raceFromCatalogue(noVenue))
    }

    // --- layPricesFromBook ---
    @Test
    fun `layPricesFromBook returns selectionId to best lay`() {
        val json = """
        {
          "marketId": "1.249508314",
          "status": "OPEN",
          "runners": [
            { "selectionId": 111, "status": "ACTIVE",
              "ex": { "availableToLay": [ { "price": 4.8, "size": 12.5 }, { "price": 5.0, "size": 25.0 } ] } },
            { "selectionId": 222, "status": "ACTIVE",
              "ex": { "availableToLay": [] } },
            { "selectionId": 333, "status": "ACTIVE",
              "ex": { "availableToLay": [ { "price": 22.0, "size": 4.0 } ] } }
          ]
        }
        """.trimIndent()
        val result = layPricesFromBook(json)
        assertEquals(MarketBookStatus.OPEN, result.status)
        assertEquals(mapOf(111L to 4.8, 222L to null, 333L to 22.0), result.layBySelectionId)
    }

    @Test
    fun `layPricesFromBook reports SUSPENDED`() {
        val json = """
        { "marketId": "1.1", "status": "SUSPENDED", "runners": [] }
        """.trimIndent()
        val result = layPricesFromBook(json)
        assertEquals(MarketBookStatus.OTHER, result.status)
        assertTrue(result.layBySelectionId.isEmpty())
    }

    @Test
    fun `layPricesFromBook treats unknown status as OTHER`() {
        val json = """{ "marketId": "1.1", "status": "WEIRD", "runners": [] }"""
        assertEquals(MarketBookStatus.OTHER, layPricesFromBook(json).status)
    }

    // --- buildLoginBody ---
    @Test
    fun `buildLoginBody url-encodes form fields`() {
        val body = buildLoginBody(username = "alice@example.com", password = "p@ss w&d")
        // Order is fixed for stability across JVMs.
        assertEquals(
            "username=alice%40example.com&password=p%40ss+w%26d",
            body
        )
    }

    // --- buildCatalogueBody ---
    @Test
    fun `buildCatalogueBody emits expected JSON-RPC body for WIN markets`() {
        val body = buildCatalogueBody(
            marketTypeCodes = listOf("WIN"),
            countries = listOf("GB", "IE"),
            from = "2026-05-09T00:00:00Z",
            to   = "2026-05-10T00:00:00Z",
            projection = listOf("EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"),
            maxResults = 1000,
            sort = "FIRST_TO_START",
        )
        val root = com.google.gson.JsonParser.parseString(body).asJsonObject
        val filter = root.getAsJsonObject("filter")
        assertEquals("[\"7\"]", filter.getAsJsonArray("eventTypeIds").toString())
        assertEquals("[\"WIN\"]", filter.getAsJsonArray("marketTypeCodes").toString())
        assertEquals("[\"GB\",\"IE\"]", filter.getAsJsonArray("marketCountries").toString())
        assertEquals("2026-05-09T00:00:00Z",
            filter.getAsJsonObject("marketStartTime").get("from").asString)
        assertEquals("1000", root.get("maxResults").asString)
        assertEquals("FIRST_TO_START", root.get("sort").asString)
    }

    // --- buildBookBody ---
    @Test
    fun `buildBookBody emits marketIds and EX_BEST_OFFERS priceData`() {
        val body = buildBookBody(listOf("1.1", "1.2"))
        val root = com.google.gson.JsonParser.parseString(body).asJsonObject
        assertEquals("[\"1.1\",\"1.2\"]", root.getAsJsonArray("marketIds").toString())
        assertEquals("[\"EX_BEST_OFFERS\"]",
            root.getAsJsonObject("priceProjection").getAsJsonArray("priceData").toString())
    }
}
