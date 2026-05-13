package com.horsey.scraper.arb

import com.horsey.scraper.MarketType
import com.horsey.scraper.ScrapeOutput
import com.horsey.scraper.paddypower.PaddyOutput

/**
 * Closed-form each-way arbitrage margin per £1 of PaddyPower stake.
 *
 * Given a PaddyPower each-way bet (stake split 50/50 between win and
 * place legs) and Betfair lay prices on the WIN market and the matching
 * TOP_N market, returns the guaranteed profit per £1 PP stake when lay
 * stakes are chosen for equal-profit arb:
 *
 *   L_w    = p / (2·bw)
 *   L_p    = (1 + (p−1)·f) / (2·bp)
 *   margin = L_w + L_p − 1
 *
 * Positive margin = arb. Negative or zero = no arb. The math derivation
 * and a worked example are in the spec at
 * `docs/superpowers/specs/2026-05-14-arb-finder-design.md`.
 *
 * @param p   PaddyPower win decimal odds
 * @param f   each-way fraction in (0, 1] (e.g. 0.2 for 1/5 odds)
 * @param bw  Betfair WIN lay decimal price
 * @param bp  Betfair TOP_N lay decimal price (same N as PP's)
 */
fun eachWayArbMargin(p: Double, f: Double, bw: Double, bp: Double): Double {
    val lw = p / (2.0 * bw)
    val lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0
}

/**
 * Joins a Betfair `ScrapeOutput` with a PaddyPower `PaddyOutput` and
 * computes each-way arbitrage opportunities. See the spec at
 * `docs/superpowers/specs/2026-05-14-arb-finder-design.md` for the
 * normative skip rules and the math.
 *
 * Returns positive-margin opportunities sorted by margin descending.
 * Negative-or-zero-margin (race, runner) tuples are filtered out.
 */
fun findArbs(betfair: ScrapeOutput, paddy: PaddyOutput): List<Arb> {
    val betfairByRaceId = betfair.races.associateBy { it.raceId }
    val out = mutableListOf<Arb>()

    for (paddyRace in paddy.races) {
        val winMarketId = paddyRace.betfairWinMarketId ?: continue
        val betfairRace = betfairByRaceId[winMarketId] ?: continue
        val ew = paddyRace.eachWayTerms ?: continue
        val topNType = topNFromPlaces(ew.places) ?: continue
        if (topNType !in betfairRace.marketScrapedAt.keys) continue

        val betfairBySelectionId = betfairRace.runners
            .mapNotNull { r -> r.selectionId?.let { sel -> sel to r } }
            .toMap()

        for (paddyRunner in paddyRace.runners) {
            val sel = paddyRunner.selectionId ?: continue
            val betfairRunner = betfairBySelectionId[sel] ?: continue
            val ppPrice = paddyRunner.winPrice ?: continue
            val ppRaw = paddyRunner.winPriceRaw ?: continue
            val winLay = betfairRunner.lay[MarketType.WIN] ?: continue
            val topNLay = betfairRunner.lay[topNType] ?: continue

            val margin = eachWayArbMargin(p = ppPrice, f = ew.fraction, bw = winLay, bp = topNLay)
            if (margin <= 0.0) continue

            out += Arb(
                venue = paddyRace.venue,
                country = paddyRace.country,
                offTime = paddyRace.offTime,
                marketName = paddyRace.marketName,
                betfairWinMarketId = winMarketId,
                runner = ArbRunner(name = paddyRunner.name, selectionId = sel),
                paddypower = PaddyPriceLeg(winPrice = ppPrice, winPriceRaw = ppRaw, eachWayTerms = ew),
                betfair = BetfairLayLeg(winLay = winLay, topNLay = topNLay, topNType = topNType),
                margin = margin,
            )
        }
    }
    return out.sortedByDescending { it.margin }
}

private fun topNFromPlaces(n: Int): MarketType? = when (n) {
    2 -> MarketType.TOP_2
    3 -> MarketType.TOP_3
    4 -> MarketType.TOP_4
    5 -> MarketType.TOP_5
    else -> null
}
