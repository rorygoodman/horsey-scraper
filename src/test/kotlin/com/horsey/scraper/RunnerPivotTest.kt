package com.horsey.scraper

import java.io.ByteArrayOutputStream
import java.io.PrintStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RunnerPivotTest {
    private fun captureStderr(block: () -> Unit): String {
        val buf = ByteArrayOutputStream()
        val original = System.err
        System.setErr(PrintStream(buf))
        try {
            block()
        } finally {
            System.setErr(original)
        }
        return buf.toString()
    }

    @Test
    fun `pivots runners across all five markets`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf("Some Horse" to 4.8, "Outsider" to 22.0))
        val top2 = MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z",
            listOf("Some Horse" to 2.5, "Outsider" to 9.5))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("Some Horse" to 1.7, "Outsider" to 5.0))
        val top4 = MarketScrape(MarketType.TOP_4, "2026-05-09T12:00:14Z",
            listOf("Some Horse" to 1.4, "Outsider" to 3.2))
        val top5 = MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z",
            listOf("Some Horse" to 1.2, "Outsider" to 2.4))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(
                MarketType.WIN to win, MarketType.TOP_2 to top2, MarketType.TOP_3 to top3,
                MarketType.TOP_4 to top4, MarketType.TOP_5 to top5
            ),
            raceIdForWarnings = "1.111"
        )

        assertEquals(2, runners.size)
        assertEquals("Some Horse", runners[0].name)
        assertEquals(
            mapOf(MarketType.WIN to 4.8, MarketType.TOP_2 to 2.5, MarketType.TOP_3 to 1.7,
                  MarketType.TOP_4 to 1.4, MarketType.TOP_5 to 1.2),
            runners[0].lay
        )
    }

    @Test
    fun `omits keys for markets that were not scraped`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to 1.5))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )

        assertEquals(1, runners.size)
        assertEquals(setOf(MarketType.WIN, MarketType.TOP_3), runners[0].lay.keys)
    }

    @Test
    fun `preserves null lay for runner with no offer in a scraped market`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to null))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        assertEquals(mapOf(MarketType.WIN to 3.0, MarketType.TOP_3 to null), runners[0].lay)
    }

    @Test
    fun `runner missing from a scraped Top-N market gets null for that key`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z",
            listOf("X" to 3.0, "Y" to 10.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("X" to 1.5))  // Y missing

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        val y = runners.single { it.name == "Y" }
        assertEquals(mapOf(MarketType.WIN to 10.0, MarketType.TOP_3 to null), y.lay)
    }

    @Test
    fun `phantom horse in Top-N is dropped with stderr warning`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z",
            listOf("X" to 1.5, "Phantom" to 7.0))

        var runners: List<RunnerOdds> = emptyList()
        val stderr = captureStderr {
            runners = pivotMarketScrapes(
                scrapes = mapOf(MarketType.WIN to win, MarketType.TOP_3 to top3),
                raceIdForWarnings = "1.111"
            )
        }
        assertEquals(listOf("X"), runners.map { it.name })
        assertTrue("Phantom horse 'Phantom' in TOP_3 for race 1.111 — dropping" in stderr,
            "stderr was: $stderr")
    }

    @Test
    fun `returns empty list when WIN scrape is absent`() {
        val top3 = MarketScrape(MarketType.TOP_3, "2026-05-09T12:00:11Z", listOf("X" to 1.5))
        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.TOP_3 to top3),
            raceIdForWarnings = "1.111"
        )
        assertEquals(emptyList(), runners)
    }

    @Test
    fun `lay map preserves MarketType declared order`() {
        val win = MarketScrape(MarketType.WIN, "2026-05-09T12:00:04Z", listOf("X" to 3.0))
        val top5 = MarketScrape(MarketType.TOP_5, "2026-05-09T12:00:17Z", listOf("X" to 1.1))
        val top2 = MarketScrape(MarketType.TOP_2, "2026-05-09T12:00:08Z", listOf("X" to 2.0))

        val runners = pivotMarketScrapes(
            scrapes = mapOf(MarketType.TOP_5 to top5, MarketType.WIN to win, MarketType.TOP_2 to top2),
            raceIdForWarnings = "1.111"
        )
        assertEquals(listOf(MarketType.WIN, MarketType.TOP_2, MarketType.TOP_5),
            runners[0].lay.keys.toList())
    }
}
