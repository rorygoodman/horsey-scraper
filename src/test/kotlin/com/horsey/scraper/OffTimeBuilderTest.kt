package com.horsey.scraper

import java.time.LocalDate
import java.time.ZoneId
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class OffTimeBuilderTest {
    private val london = ZoneId.of("Europe/London")

    @Test
    fun `builds BST off-time during summer`() {
        val date = LocalDate.of(2026, 5, 9)
        assertEquals("2026-05-09T13:30:00+01:00", buildOffTime("13:30", date, london))
    }

    @Test
    fun `builds GMT off-time during winter`() {
        val date = LocalDate.of(2026, 1, 15)
        assertEquals("2026-01-15T13:30:00Z", buildOffTime("13:30", date, london))
    }

    @Test
    fun `accepts single-digit hour`() {
        val date = LocalDate.of(2026, 5, 9)
        assertEquals("2026-05-09T09:05:00+01:00", buildOffTime("9:05", date, london))
    }

    @Test
    fun `returns null on malformed input`() {
        val date = LocalDate.of(2026, 5, 9)
        assertNull(buildOffTime("not-a-time", date, london))
        assertNull(buildOffTime("25:00", date, london))
        assertNull(buildOffTime("", date, london))
    }
}
