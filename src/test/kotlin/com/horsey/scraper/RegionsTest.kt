package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RegionsTest {
    @Test
    fun `gb-ie maps to GB and IE`() {
        assertEquals(setOf("GB", "IE"), Regions.countriesFor("gb-ie"))
    }

    @Test
    fun `us maps to US`() {
        assertEquals(setOf("US"), Regions.countriesFor("us"))
    }

    @Test
    fun `unknown region returns null`() {
        assertNull(Regions.countriesFor("fr"))
    }

    @Test
    fun `all returns both regions`() {
        assertEquals(setOf("gb-ie", "us"), Regions.ALL)
    }

    @Test
    fun `countriesForAll unions all selected regions`() {
        assertEquals(setOf("GB", "IE", "US"), Regions.countriesForAll(setOf("gb-ie", "us")))
        assertEquals(setOf("GB", "IE"), Regions.countriesForAll(setOf("gb-ie")))
        assertEquals(setOf("US"), Regions.countriesForAll(setOf("us")))
    }
}
