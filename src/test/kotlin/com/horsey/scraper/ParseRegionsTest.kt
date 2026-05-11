package com.horsey.scraper

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ParseRegionsTest {
    @Test
    fun `defaults to gb-ie when no arg`() {
        assertEquals(setOf("gb-ie"), parseRegions(emptyArray()))
    }

    @Test
    fun `accepts us only`() {
        assertEquals(setOf("us"), parseRegions(arrayOf("us")))
    }

    @Test
    fun `accepts comma-separated list`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("gb-ie,us")))
    }

    @Test
    fun `accepts uppercase`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf("GB-IE,US")))
    }

    @Test
    fun `trims whitespace around ids`() {
        assertEquals(setOf("gb-ie", "us"), parseRegions(arrayOf(" gb-ie , us ")))
    }

    @Test
    fun `rejects unknown region with helpful message listing valid ids`() {
        val e = assertFailsWith<IllegalArgumentException> {
            parseRegions(arrayOf("fr"))
        }
        assertTrue("fr" in (e.message ?: ""), "message must mention the bad id: ${e.message}")
        assertTrue("gb-ie" in (e.message ?: "") && "us" in (e.message ?: ""),
            "message must list valid ids: ${e.message}")
    }

    @Test
    fun `rejects empty string`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf("")) }
    }

    @Test
    fun `rejects single comma (no real ids)`() {
        assertFailsWith<IllegalArgumentException> { parseRegions(arrayOf(",")) }
    }
}
