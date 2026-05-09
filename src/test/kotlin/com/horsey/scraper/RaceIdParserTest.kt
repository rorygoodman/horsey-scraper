package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RaceIdParserTest {
    @Test
    fun `extracts ID from canonical market URL`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `extracts ID with trailing slash`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314/"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `extracts ID with query string`() {
        val url = "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314?source=foo"
        assertEquals("1.249508314", extractRaceId(url))
    }

    @Test
    fun `returns null when no 1-dot-digits segment present`() {
        assertNull(extractRaceId("https://www.betfair.com/exchange/plus/en/horse-racing"))
    }

    @Test
    fun `returns null on empty input`() {
        assertNull(extractRaceId(""))
    }
}
