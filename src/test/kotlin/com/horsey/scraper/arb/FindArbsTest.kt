package com.horsey.scraper.arb

import com.horsey.scraper.MarketType
import com.horsey.scraper.RaceOdds
import com.horsey.scraper.RunnerOdds
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.EachWayTerms
import com.horsey.scraper.paddypower.PaddyOutput
import com.horsey.scraper.paddypower.PaddyRace
import com.horsey.scraper.paddypower.PaddyRunner
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FindArbsTest {

    private val betfairScrapedAt = "2026-05-13T22:00:00Z"
    private val paddyScrapedAt = "2026-05-13T22:00:01Z"

    @Test
    fun `one race, one runner, prices skewed yields one arb`() {
        // Champ example: p=11, f=0.2, bw=10, bp=2.5 → margin 0.15
        val betfair = ScrapeOutput(
            scrapedAt = betfairScrapedAt, raceCount = 1,
            races = listOf(
                raceOdds(
                    raceId = "1.x",
                    runners = listOf(
                        runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5)),
                    ),
                    scrapedMarkets = setOf(MarketType.WIN, MarketType.TOP_4),
                ),
            ),
        )
        val paddy = PaddyOutput(
            scrapedAt = paddyScrapedAt, raceCount = 1,
            races = listOf(
                paddyRace(
                    betfairId = "1.x",
                    runners = listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")),
                    ew = EachWayTerms(0.2, 4),
                ),
            ),
        )
        val arbs = findArbs(betfair, paddy)
        assertEquals(1, arbs.size)
        val arb = arbs.first()
        assertEquals("Champ", arb.runner.name)
        assertEquals(1001L, arb.runner.selectionId)
        assertEquals(0.15, arb.margin, 1e-9)
        assertEquals(MarketType.TOP_4, arb.betfair.topNType)
    }

    @Test
    fun `equilibrium prices yield no arb`() {
        val p = 11.0; val f = 0.2
        val bp = 1.0 + (p - 1.0) * f  // 3.0
        val betfair = ScrapeOutput(
            scrapedAt = betfairScrapedAt, raceCount = 1,
            races = listOf(
                raceOdds(
                    raceId = "1.x",
                    runners = listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to p, MarketType.TOP_4 to bp))),
                    scrapedMarkets = setOf(MarketType.WIN, MarketType.TOP_4),
                ),
            ),
        )
        val paddy = PaddyOutput(
            scrapedAt = paddyScrapedAt, raceCount = 1,
            races = listOf(
                paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, p, "10/1")), EachWayTerms(f, 4)),
            ),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `race in PaddyPower but not Betfair is skipped`() {
        val betfair = ScrapeOutput(betfairScrapedAt, 0, emptyList())
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("X", 1L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `race in Betfair but not PaddyPower is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("X", 1L, mapOf(MarketType.WIN to 5.0, MarketType.TOP_4 to 2.0))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(paddyScrapedAt, 0, emptyList())
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `runner in PaddyPower with no matching selectionId in Betfair is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Other", 999L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `PaddyPower race with null eachWayTerms is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), ew = null)),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `Betfair race missing the matching TOP_N market is skipped`() {
        // PP wants 4 places, BF only scraped WIN + TOP_2.
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_2 to 5.0))),
                setOf(MarketType.WIN, MarketType.TOP_2),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `runner with null lay price on either market is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to null, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `non-runner on PaddyPower side is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x",
                listOf(PaddyRunner(name = "Champ", selectionId = 1001L, winPrice = null, winPriceRaw = null)),
                EachWayTerms(0.2, 4))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `eachWayTerms_places outside 2 to 5 is skipped`() {
        val betfair = ScrapeOutput(
            betfairScrapedAt, 1,
            listOf(raceOdds("1.x",
                listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                setOf(MarketType.WIN, MarketType.TOP_4),
            )),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 1,
            listOf(paddyRace("1.x", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 6))),
        )
        assertTrue(findArbs(betfair, paddy).isEmpty())
    }

    @Test
    fun `multiple positive arbs are sorted by margin descending`() {
        // Race A: margin 0.15 (Champ example).
        // Race B: same setup but bp=2.0 → bigger arb.
        val betfair = ScrapeOutput(
            betfairScrapedAt, 2,
            listOf(
                raceOdds("1.A",
                    listOf(runner("Champ", 1001L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.5))),
                    setOf(MarketType.WIN, MarketType.TOP_4)),
                raceOdds("1.B",
                    listOf(runner("Hero", 2002L, mapOf(MarketType.WIN to 10.0, MarketType.TOP_4 to 2.0))),
                    setOf(MarketType.WIN, MarketType.TOP_4)),
            ),
        )
        val paddy = PaddyOutput(
            paddyScrapedAt, 2,
            listOf(
                paddyRace("1.A", listOf(paddyRunner("Champ", 1001L, 11.0, "10/1")), EachWayTerms(0.2, 4)),
                paddyRace("1.B", listOf(paddyRunner("Hero", 2002L, 11.0, "10/1")), EachWayTerms(0.2, 4)),
            ),
        )
        val arbs = findArbs(betfair, paddy)
        assertEquals(2, arbs.size)
        assertTrue(arbs[0].margin > arbs[1].margin, "expected descending margin order: $arbs")
        assertEquals("Hero", arbs[0].runner.name)
    }

    // --- helpers ---

    private fun raceOdds(
        raceId: String,
        runners: List<RunnerOdds>,
        scrapedMarkets: Set<MarketType>,
    ): RaceOdds {
        val msa = linkedMapOf<MarketType, String>()
        for (m in MarketType.values()) if (m in scrapedMarkets) msa[m] = betfairScrapedAt
        return RaceOdds(
            raceId = raceId,
            venue = "Lingfield",
            country = "GB",
            offTime = "2026-05-14T17:40:00+01:00",
            winMarketUrl = "https://www.betfair.com/exchange/plus/horse-racing/market/$raceId",
            marketName = "17:40 Lingfield",
            marketScrapedAt = msa,
            runners = runners,
        )
    }

    private fun runner(name: String, selectionId: Long, lay: Map<MarketType, Double?>): RunnerOdds =
        RunnerOdds(name = name, lay = lay, selectionId = selectionId)

    private fun paddyRace(
        betfairId: String,
        runners: List<PaddyRunner>,
        ew: EachWayTerms?,
    ): PaddyRace = PaddyRace(
        venue = "Lingfield",
        country = "GB",
        offTime = "2026-05-14T17:40:00+01:00",
        marketName = "17:40 Lingfield",
        raceUrl = "",
        scrapedAt = paddyScrapedAt,
        betfairWinMarketId = betfairId,
        eachWayTerms = ew,
        runners = runners,
    )

    private fun paddyRunner(name: String, selectionId: Long, winPrice: Double, raw: String): PaddyRunner =
        PaddyRunner(name = name, selectionId = selectionId, winPrice = winPrice, winPriceRaw = raw)
}
