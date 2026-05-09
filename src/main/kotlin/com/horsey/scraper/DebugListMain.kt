package com.horsey.scraper

import org.openqa.selenium.JavascriptExecutor
import java.io.File

/**
 * Debug entry point — loads the Betfair horse-racing landing page and dumps
 * everything useful for figuring out the DOM. Saves a copy of the rendered
 * HTML for offline inspection too.
 */
fun main() {
    val url = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7"
    val driver = createChromeDriver()
    try {
        driver.get(url)
        // Don't wait on a specific selector — page may have a cookie banner or differ.
        Thread.sleep(8000)

        val js = driver as JavascriptExecutor

        // 1. Page title + URL after redirects.
        println("Final URL : ${driver.currentUrl}")
        println("Page title: ${driver.title}")
        println("Body length: ${(js.executeScript("return document.body.innerText.length") as Long)}")
        println("=".repeat(80))

        // 2. Aggregate anchor href patterns (group by path prefix, count).
        @Suppress("UNCHECKED_CAST")
        val patterns = js.executeScript("""
            var counts = {};
            var anchors = document.querySelectorAll('a[href]');
            for (var i = 0; i < anchors.length; i++) {
                var h = anchors[i].getAttribute('href') || '';
                // bucket by first 4 path segments
                var path = h.split('?')[0];
                var parts = path.split('/').slice(0, 6).join('/');
                counts[parts] = (counts[parts] || 0) + 1;
            }
            var rows = [];
            for (var k in counts) rows.push(k + ' => ' + counts[k]);
            return rows;
        """) as? List<String> ?: emptyList()
        println("Anchor href bucket counts (top 60):")
        patterns.sortedByDescending { it.substringAfter("=> ").trim().toIntOrNull() ?: 0 }
            .take(60)
            .forEach { println("  $it") }

        // 3. Sample a handful of likely-race anchors (text matches HH:mm).
        @Suppress("UNCHECKED_CAST")
        val timeAnchors = js.executeScript("""
            var out = [];
            var anchors = document.querySelectorAll('a[href]');
            for (var i = 0; i < anchors.length && out.length < 25; i++) {
                var a = anchors[i];
                var t = (a.textContent || '').trim();
                if (/^\d{1,2}:\d{2}$/.test(t)) {
                    out.push(t + '|||' + a.getAttribute('href'));
                }
            }
            return out;
        """) as? List<String> ?: emptyList()
        println("\nAnchors with HH:mm text (first 25):")
        timeAnchors.forEach { println("  $it") }

        // 4. Save HTML to disk for offline inspection.
        val html = js.executeScript("return document.documentElement.outerHTML") as String
        File("debug-page.html").writeText(html)
        println("\nWrote debug-page.html (${html.length} chars)")
    } finally {
        driver.quit()
    }
}
