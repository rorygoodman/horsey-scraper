package com.horsey.scraper.arb

import com.horsey.scraper.MarketType
import com.horsey.scraper.paddypower.EachWayTerms

/**
 * The PaddyPower-side prices used when computing one arb. Captured into
 * the output so the static-site consumer can recompute lay stakes from
 * the same numbers the calculator used.
 */
data class PaddyPriceLeg(
    val winPrice: Double,
    val winPriceRaw: String,
    val eachWayTerms: EachWayTerms,
)

/**
 * The Betfair-side lay prices used when computing one arb. `topNType`
 * names the specific TOP_N market chosen (matches PaddyPower's
 * `eachWayTerms.places`).
 */
data class BetfairLayLeg(
    val winLay: Double,
    val topNLay: Double,
    val topNType: MarketType,
)

/** Identification for one runner in an arb result. */
data class ArbRunner(
    val name: String,
    val selectionId: Long,
)

/**
 * One each-way arbitrage opportunity. `margin` is the per-£1
 * PaddyPower-stake profit, > 0 by construction (negative-margin
 * results are filtered out before reaching `arbs[]`).
 */
data class Arb(
    val venue: String,
    val country: String,
    val offTime: String,
    val marketName: String,
    val betfairWinMarketId: String,
    val runner: ArbRunner,
    val paddypower: PaddyPriceLeg,
    val betfair: BetfairLayLeg,
    val margin: Double,
)

/** Top-level wrapper for `arbs.json`. */
data class ArbOutput(
    val computedAt: String,
    val betfairScrapedAt: String,
    val paddypowerScrapedAt: String,
    val arbCount: Int,
    val arbs: List<Arb>,
)
