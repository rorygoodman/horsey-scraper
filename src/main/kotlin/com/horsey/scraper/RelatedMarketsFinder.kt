package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver

/**
 * Finds Top-N market URLs in the currently-loaded race page DOM.
 *
 * Returns a map containing entries only for markets actually present on the
 * page. Missing markets (e.g. TOP_5 absent for a small field) result in
 * absent keys, which is exactly what the rest of the pipeline expects.
 *
 * Selector confirmed by the T8 spike: Betfair exposes related markets in a
 * tab strip as `<a class="market-tab-label">`. We additionally filter by the
 * exact link text ("Top 2 Finish" .. "Top 5 Finish") because the same tab
 * strip also contains Each Way, AvB, and other unrelated markets.
 *
 * `a.href` (the DOM property, not the attribute) resolves the relative path
 * to an absolute URL automatically — that's what the caller will navigate to.
 *
 * Reads `driver`'s current page; does not navigate.
 */
fun findTopNUrls(driver: WebDriver): Map<MarketType, String> {
    val js = driver as JavascriptExecutor

    @Suppress("UNCHECKED_CAST")
    val raw = js.executeScript("""
        var wanted = { 'Top 2 Finish':'TOP_2', 'Top 3 Finish':'TOP_3',
                       'Top 4 Finish':'TOP_4', 'Top 5 Finish':'TOP_5' };
        var out = [];
        document.querySelectorAll('a.market-tab-label').forEach(function(a) {
            var t = (a.textContent || '').trim();
            if (wanted.hasOwnProperty(t)) {
                var href = a.href || '';  // .href property = absolute URL
                if (href && /\/market\/1\./.test(href)) {
                    out.push(wanted[t] + '|||' + href);
                }
            }
        });
        return out;
    """) as? List<String> ?: emptyList()

    val result = linkedMapOf<MarketType, String>()
    for (line in raw) {
        val parts = line.split("|||", limit = 2)
        if (parts.size != 2) continue
        val type = runCatching { MarketType.valueOf(parts[0]) }.getOrNull() ?: continue
        result.putIfAbsent(type, parts[1])  // First wins; duplicates unlikely with this selector
    }
    return result
}
