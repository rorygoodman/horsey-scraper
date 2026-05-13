package com.horsey.scraper.arb

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
