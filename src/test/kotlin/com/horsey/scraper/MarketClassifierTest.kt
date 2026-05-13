package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class MarketClassifierTest {
    @Test
    fun `Top 2 Finish with numberOfWinners 2 classifies as TOP_2`() {
        assertEquals(MarketType.TOP_2, classifyTopN("Top 2 Finish", 2))
    }

    @Test
    fun `Top 3 4 5 Finish classify correctly`() {
        assertEquals(MarketType.TOP_3, classifyTopN("Top 3 Finish", 3))
        assertEquals(MarketType.TOP_4, classifyTopN("Top 4 Finish", 4))
        assertEquals(MarketType.TOP_5, classifyTopN("Top 5 Finish", 5))
    }

    @Test
    fun `case insensitive on name`() {
        assertEquals(MarketType.TOP_3, classifyTopN("top 3 finish", 3))
        assertEquals(MarketType.TOP_4, classifyTopN("TOP 4 FINISH", 4))
    }

    @Test
    fun `name N and numberOfWinners must match`() {
        assertNull(classifyTopN("Top 3 Finish", 2))
        assertNull(classifyTopN("Top 4 Finish", 5))
    }

    @Test
    fun `To Be Placed market is rejected`() {
        assertNull(classifyTopN("To Be Placed", 2))
        assertNull(classifyTopN("To Be Placed", 3))
    }

    @Test
    fun `arbitrary other names are rejected`() {
        assertNull(classifyTopN("Each Way", 2))
        assertNull(classifyTopN("Without Favourite", 1))
        assertNull(classifyTopN("Top 6 Finish", 6))
        assertNull(classifyTopN("Top 1 Finish", 1))
    }

    @Test
    fun `whitespace-padded name is accepted`() {
        assertEquals(MarketType.TOP_2, classifyTopN("  Top 2 Finish  ", 2))
    }

    // --- API-style "N TBP" name format (Betfair REST returns this, not UI text) ---

    @Test
    fun `N TBP API name classifies as TOP_N`() {
        assertEquals(MarketType.TOP_2, classifyTopN("2 TBP", null))
        assertEquals(MarketType.TOP_3, classifyTopN("3 TBP", null))
        assertEquals(MarketType.TOP_4, classifyTopN("4 TBP", null))
        assertEquals(MarketType.TOP_5, classifyTopN("5 TBP", null))
    }

    @Test
    fun `N TBP is case-insensitive and whitespace-tolerant`() {
        assertEquals(MarketType.TOP_2, classifyTopN("2 tbp", null))
        assertEquals(MarketType.TOP_4, classifyTopN(" 4 TBP ", null))
    }

    @Test
    fun `N TBP out of range is rejected`() {
        assertNull(classifyTopN("1 TBP", null))
        assertNull(classifyTopN("6 TBP", null))
    }

    @Test
    fun `null numberOfWinners is accepted for either name format`() {
        assertEquals(MarketType.TOP_2, classifyTopN("Top 2 Finish", null))
        assertEquals(MarketType.TOP_3, classifyTopN("3 TBP", null))
    }

    @Test
    fun `non-null numberOfWinners still must agree with N`() {
        assertEquals(MarketType.TOP_2, classifyTopN("2 TBP", 2))
        assertNull(classifyTopN("2 TBP", 3))
    }
}
