package com.horsey.scraper.arb

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ArbMainCliTest {

    @Test
    fun `zero args yields all defaults`() {
        val paths = parseArbCliArgs(emptyArray())
        assertEquals("betfair.json", paths.betfairInput)
        assertEquals("paddypower.json", paths.paddypowerInput)
        assertEquals("arbs.json", paths.output)
    }

    @Test
    fun `three args explicit`() {
        val paths = parseArbCliArgs(arrayOf("a.json", "b.json", "c.json"))
        assertEquals("a.json", paths.betfairInput)
        assertEquals("b.json", paths.paddypowerInput)
        assertEquals("c.json", paths.output)
    }

    @Test
    fun `one arg rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a.json")) }
    }

    @Test
    fun `two args rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a.json", "b.json")) }
    }

    @Test
    fun `four args rejected`() {
        assertFailsWith<IllegalArgumentException> { parseArbCliArgs(arrayOf("a", "b", "c", "d")) }
    }
}
