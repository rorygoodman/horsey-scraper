package com.horsey.scraper.arb

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class EachWayArbMarginTest {

    @Test
    fun `Champ example 11_0 win 1_5 odds 4 places vs BF 10 and 2_5 yields 0_15 margin`() {
        // p=11.0, f=0.2, bw=10.0, bp=2.5
        // L_w = 11/(2*10) = 0.55
        // L_p = (1 + (11-1)*0.2) / (2*2.5) = 3/5 = 0.60
        // margin = 0.55 + 0.60 - 1 = 0.15
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 10.0, bp = 2.5)
        assertEquals(0.15, m, 1e-9)
    }

    @Test
    fun `equilibrium gives margin of zero`() {
        // bw == p and bp == 1 + (p-1)*f → margin == 0
        val p = 7.0
        val f = 0.25
        val bp = 1.0 + (p - 1.0) * f  // 1 + 6*0.25 = 2.5
        val m = eachWayArbMargin(p = p, f = f, bw = p, bp = bp)
        assertTrue(abs(m) < 1e-12, "expected ~0, got $m")
    }

    @Test
    fun `wider Betfair prices give negative margin`() {
        // BF lay prices wider than equilibrium → negative margin (no arb).
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 15.0, bp = 4.0)
        assertTrue(m < 0.0, "expected negative margin, got $m")
    }

    @Test
    fun `bp of 1_0 yields a finite (huge) result, not NaN`() {
        // bp = 1.0 means decimal odds 1.0 (100% probability, never lays).
        // L_p = (1 + (p-1)*f) / (2*1.0) = blow-up
        val m = eachWayArbMargin(p = 11.0, f = 0.2, bw = 10.0, bp = 1.0)
        assertTrue(m.isFinite(), "margin must be finite, got $m")
        assertTrue(m > 0.0, "margin should be very positive, got $m")
    }

    @Test
    fun `1_4 odds 5 places worked example`() {
        // p=6.0 (5/1), f=0.25 (1/4 odds), bw=5.5, bp=2.0
        // L_w = 6/11 = 0.5454545...
        // L_p = (1 + 5*0.25) / (2*2.0) = 2.25/4 = 0.5625
        // margin = 0.5454545... + 0.5625 - 1 = 0.10795454...
        val m = eachWayArbMargin(p = 6.0, f = 0.25, bw = 5.5, bp = 2.0)
        val expected = 6.0 / (2.0 * 5.5) + (1.0 + (6.0 - 1.0) * 0.25) / (2.0 * 2.0) - 1.0
        assertEquals(expected, m, 1e-12)
    }

    @Test
    fun `f of zero collapses to a degenerate case (no place leg payout)`() {
        // L_p = 1 / (2*bp). Margin can still be non-zero but the place
        // leg of the EW pays nothing. The function should still return
        // a finite number — caller is responsible for filtering EW=null.
        val m = eachWayArbMargin(p = 5.0, f = 0.0, bw = 5.0, bp = 2.0)
        assertTrue(m.isFinite())
    }
}
