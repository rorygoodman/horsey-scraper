package com.horsey.scraper

import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RaceListFetcherTest {
    @Test
    fun `londonDayWindowUtc returns midnight-to-midnight London-local in UTC for a BST day`() {
        // 2026-05-11: BST, London is UTC+1. So midnight London = 23:00 prev UTC.
        val (from, to) = londonDayWindowUtc(LocalDate.parse("2026-05-11"))
        assertEquals("2026-05-10T23:00:00Z", from)
        assertEquals("2026-05-11T23:00:00Z", to)
    }

    @Test
    fun `londonDayWindowUtc returns midnight-to-midnight London-local in UTC for a GMT day`() {
        // 2026-01-15: GMT, London is UTC+0.
        val (from, to) = londonDayWindowUtc(LocalDate.parse("2026-01-15"))
        assertEquals("2026-01-15T00:00:00Z", from)
        assertEquals("2026-01-16T00:00:00Z", to)
    }

    @Test
    fun `parseCatalogueRaces shreds a list response into Race objects`() {
        val json = """
        [
          {
            "marketId": "1.1",
            "marketName": "5f Hcap",
            "marketStartTime": "2026-05-09T12:30:00.000Z",
            "description": { "marketType": "WIN", "numberOfWinners": 1 },
            "event": { "id": "10", "countryCode": "GB", "venue": "Lingfield" }
          },
          {
            "marketId": "1.2",
            "marketName": "Mdn",
            "marketStartTime": "2026-05-09T13:00:00.000Z",
            "description": { "marketType": "WIN", "numberOfWinners": 1 },
            "event": { "id": "20", "countryCode": "IE", "venue": "Naas" }
          }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(2, races.size)
        assertEquals("1.1", races[0].raceId)
        assertEquals("Naas", races[1].venue)
        assertEquals("IE", races[1].country)
    }

    @Test
    fun `parseCatalogueRaces sorts by offTime then venue and dedupes`() {
        val json = """
        [
          { "marketId": "1.B", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "GB", "venue": "Bath" } },
          { "marketId": "1.A", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "10", "countryCode": "GB", "venue": "Lingfield" } },
          { "marketId": "1.B", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "GB", "venue": "Bath" } }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(listOf("1.A", "1.B"), races.map { it.raceId })
    }

    @Test
    fun `parseCatalogueRaces skips entries with missing required fields`() {
        val json = """
        [
          { "marketId": "1.1", "marketStartTime": "2026-05-09T12:30:00.000Z",
            "event": { "id": "10", "countryCode": "GB" } },
          { "marketId": "1.2", "marketStartTime": "2026-05-09T13:00:00.000Z",
            "event": { "id": "20", "countryCode": "IE", "venue": "Naas" } }
        ]
        """.trimIndent()
        val races = parseCatalogueRaces(json)
        assertEquals(listOf("1.2"), races.map { it.raceId })
    }

    @Test
    fun `parseCatalogueRaces returns empty on empty array`() {
        assertTrue(parseCatalogueRaces("[]").isEmpty())
    }
}
