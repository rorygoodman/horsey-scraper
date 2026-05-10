package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor

/**
 * Spike: load a Win market URL and dump candidate elements that could hold
 * the race "market name" (e.g. "13:30 Lingfield - 5f Hcap").
 *
 * Run with:
 *   ./gradlew run -PmainClass=com.horsey.scraper.DebugMarketNameKt --args='<win-market-url>' --quiet
 *
 * BetfairRaceScraper.extractMarketName currently uses `h1` and is hitting an
 * empty/missing element on every race we've smoke-tested, falling back to the
 * "<offTime> <venue>" string. This spike finds the right selector.
 */
fun main(args: Array<String>) {
    val url = args.firstOrNull() ?: error("Pass a Win market URL as the first argument")
    val driver = createChromeDriver()
    try {
        driver.get(url)
        Thread.sleep(8000)  // crude wait for SPA to settle
        val js = driver as JavascriptExecutor

        @Suppress("UNCHECKED_CAST")
        val report = js.executeScript("""
            function dump(label, selector) {
                var rows = [];
                document.querySelectorAll(selector).forEach(function(el, i) {
                    var t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
                    var cls = el.getAttribute('class') || '';
                    rows.push(label + '[' + i + '] tag=' + el.tagName +
                              ' class="' + cls + '" text="' + t + '"');
                });
                return rows;
            }
            var out = [];
            out.push('document.title="' + document.title + '"');
            out = out.concat(dump('h1', 'h1'));
            out = out.concat(dump('h2', 'h2'));
            out = out.concat(dump('h3.runner-name (skip — runner names)', 'h3.runner-name').slice(0, 0));
            out = out.concat(dump('[class*="market-name"]', '[class*="market-name"]'));
            out = out.concat(dump('[class*="market-title"]', '[class*="market-title"]'));
            out = out.concat(dump('[class*="market-info"]', '[class*="market-info"]'));
            out = out.concat(dump('[class*="event-name"]', '[class*="event-name"]'));
            out = out.concat(dump('[class*="market-header"]', '[class*="market-header"]'));
            out = out.concat(dump('.market-tab-label.active', '.market-tab-label.active'));
            return out;
        """) as List<String>

        println("==== Market-name dump for $url ====")
        report.forEach(::println)
        println("==== ${report.size} entries ====")
    } finally {
        driver.quit()
    }
}
