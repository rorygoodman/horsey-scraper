package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals

class MarketTypeTest {
    @Test
    fun `has the five expected values in declared order`() {
        assertEquals(
            listOf("WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"),
            MarketType.values().map { it.name }
        )
    }
}
