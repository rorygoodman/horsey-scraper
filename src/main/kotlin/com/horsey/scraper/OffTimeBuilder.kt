package com.horsey.scraper

import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val HHMM = Regex("""^(\d{1,2}):(\d{2})$""")

/**
 * Builds an ISO-8601 timestamp string with offset for a race off-time.
 *
 * Combines `hhmm` (e.g. "13:30" or "9:05") with `date` interpreted in `zone`
 * to produce a string like "2026-05-09T13:30:00+01:00" (BST) or
 * "2026-01-15T13:30:00Z" (GMT).
 *
 * Returns null on malformed input.
 */
fun buildOffTime(hhmm: String, date: LocalDate, zone: ZoneId): String? {
    val match = HHMM.matchEntire(hhmm) ?: return null
    val hour = match.groupValues[1].toInt()
    val minute = match.groupValues[2].toInt()
    if (hour !in 0..23 || minute !in 0..59) return null
    val time = LocalTime.of(hour, minute)
    val zoned = date.atTime(time).atZone(zone)
    return zoned.toOffsetDateTime().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
}
