package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor

// Findings from 2026-05-09 dump against https://www.betfair.com/exchange/plus/horse-racing/market/1.257887405
//   (14:55 1m4f Hcap, 5-runner field)
//
//   Top-N markets exposed via TWO sources (use either; market-tab-label is cleaner):
//     1. Sidebar nav:  selector  a[href*="/market/1."]  with class "navigation-link    MARKET  "
//        — these carry a ?nodeId= query param in the href
//     2. Market tabs:  selector  a.market-tab-label  (parent li.generic-tab.small)
//        — clean relative hrefs with no query param; PREFERRED selector for T9
//
//   Each Top-N link is an <A> element with text exactly "Top N Finish"
//   (e.g. "Top 3 Finish", "Top 4 Finish").
//
//   href format: relative path  horse-racing/market/1.<marketId>
//     e.g. horse-racing/market/1.257887406  (no leading slash, no nodeId param on tab links)
//   To make absolute: prepend  https://www.betfair.com/exchange/plus/
//
//   Notes:
//     - This 5-runner handicap exposed Top 3 and Top 4 Finish only — no Top 2 or Top 5.
//       Top-N availability varies by runner count and market; T9 must handle absent markets gracefully.
//     - The sidebar LI wrapper (class "node node<marketId>") has no href itself; the child <A> does.
//     - TEXT-MATCH confirmed: tag=A, href="horse-racing/market/1.NNN", class="navigation-link    MARKET  "
//       and tag=A, href="horse-racing/market/1.NNN", class="market-tab-label"
//     - Each Way and AvB markets also appear in the same tab row; filter by /^Top \d+ Finish$/ text.
//     - Recommended T9 selector:  a.market-tab-label  filtered to text matching /^Top \d+ Finish$/

/**
 * Spike: load a Win market URL (passed as the first arg, or default below)
 * and dump everything that could be a related-market link. Read the output
 * and use it to write the selectors used in RelatedMarketsFinder.
 *
 * Run with:
 *   ./gradlew run -PmainClass=com.horsey.scraper.DebugMarketLinksKt --args='https://www.betfair.com/exchange/plus/en/horse-racing/market/1.NNN'
 *
 * Or, after a real run of Main, copy any race URL from data.json.
 */
fun main(args: Array<String>) {
    val url = args.firstOrNull() ?: error(
        "Pass a Win market URL as the first argument, e.g. " +
        "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314"
    )
    val driver = createChromeDriver()
    try {
        driver.get(url)
        Thread.sleep(8000)  // crude wait for SPA to settle
        val js = driver as JavascriptExecutor

        @Suppress("UNCHECKED_CAST")
        val report = js.executeScript("""
            function dump(selector) {
                var rows = [];
                document.querySelectorAll(selector).forEach(function(el) {
                    var t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
                    var href = el.getAttribute('href') || '';
                    var cls = el.getAttribute('class') || '';
                    rows.push(selector + ' | text="' + t + '" | href="' + href + '" | class="' + cls + '"');
                });
                return rows;
            }
            var out = [];
            // Likely places: sidebar nav, market-tabs, dropdowns
            ['a[href*="/market/1."]', 'li.market-item', 'a.market-link',
             '.market-list a', '.related-markets a', 'nav a',
             '[class*="market"] a'].forEach(function(sel) {
                out = out.concat(dump(sel));
            });
            // Anything containing "Top" or "To Be Placed" anywhere
            document.querySelectorAll('a, button, li').forEach(function(el) {
                var t = (el.textContent || '').trim();
                if (/^Top \d+ /.test(t) || /^To Be Placed/i.test(t)) {
                    out.push('TEXT-MATCH | tag=' + el.tagName + ' | text="' + t.slice(0,60) +
                             '" | href="' + (el.getAttribute('href') || '') +
                             '" | class="' + (el.getAttribute('class') || '') + '"');
                }
            });
            return out;
        """) as List<String>

        println("==== Related-markets dump for $url ====")
        report.forEach(::println)
        println("==== ${report.size} candidate elements ====")
    } finally {
        driver.quit()
    }
}
