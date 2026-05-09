package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver
import org.openqa.selenium.WebElement
import org.openqa.selenium.support.ui.ExpectedConditions
import org.openqa.selenium.support.ui.WebDriverWait
import java.time.Duration
import java.time.Instant

/**
 * Scrapes a single Betfair Exchange market page that is already loaded in
 * `driver`. Returns a [MarketScrape] with one entry per visible runner; the
 * lay value is null where no lay is currently on offer.
 *
 * Caller is responsible for navigating `driver` to the market URL before
 * calling this. We wait up to 20s for runner rows to appear.
 *
 * For markets with many runners, a virtual-scroll loop walks the runner list
 * to pick up entries beyond the initial viewport. Most horse races finish in
 * one pass; the loop is harmless when nothing scrolls.
 */
fun scrapeLoadedMarket(driver: WebDriver, type: MarketType): MarketScrape {
    waitForRunners(driver)
    val runners = scrollAndExtract(driver as JavascriptExecutor)
    return MarketScrape(
        type = type,
        scrapedAt = Instant.now().toString(),
        runners = runners
    )
}

private fun waitForRunners(driver: WebDriver) {
    val wait = WebDriverWait(driver, Duration.ofSeconds(20))
    wait.until(
        ExpectedConditions.presenceOfElementLocated(By.cssSelector("tr.runner-line, h3.runner-name"))
    )
    Thread.sleep(2000)
}

private fun scrollAndExtract(js: JavascriptExecutor): List<Pair<String, Double?>> {
    val map = linkedMapOf<String, Double?>()
    val scrollContainer = findScrollableContainer(js)
    if (scrollContainer == null) {
        collectVisible(js, map)
        return map.toList()
    }

    val clientHeight = js.executeScript("return arguments[0].clientHeight;", scrollContainer) as Long
    js.executeScript("arguments[0].scrollTop = 0;", scrollContainer)
    Thread.sleep(400)

    var noNewCount = 0
    while (noNewCount < 6) {
        val previousSize = map.size
        collectVisible(js, map)
        if (map.size > previousSize) noNewCount = 0 else noNewCount++

        js.executeScript(
            "arguments[0].scrollTop += arguments[1];",
            scrollContainer,
            (clientHeight * 0.6).toLong()
        )
        Thread.sleep(500)

        val atBottom = js.executeScript(
            "var el = arguments[0]; return el.scrollTop + el.clientHeight >= el.scrollHeight - 5;",
            scrollContainer
        ) as Boolean
        if (atBottom) {
            collectVisible(js, map)
            break
        }
    }
    return map.toList()
}

private fun findScrollableContainer(js: JavascriptExecutor): WebElement? {
    return try {
        js.executeScript("""
            var runner = document.querySelector('h3.runner-name');
            if (runner) {
                var el = runner.parentElement;
                while (el && el !== document.body && el !== document.documentElement) {
                    var style = window.getComputedStyle(el);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 20) {
                        return el;
                    }
                    el = el.parentElement;
                }
            }
            return null;
        """) as? WebElement
    } catch (e: Exception) {
        null
    }
}

@Suppress("UNCHECKED_CAST")
private fun collectVisible(js: JavascriptExecutor, into: MutableMap<String, Double?>) {
    try {
        val results = js.executeScript("""
            var out = [];
            var rows = document.querySelectorAll('tr.runner-line');
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var nameEl = row.querySelector('h3.runner-name');
                if (!nameEl) continue;
                var name = nameEl.textContent.trim();
                if (!name) continue;

                var price = '';
                var layCell = row.querySelector('td.first-lay-cell');
                if (layCell) {
                    var label = layCell.querySelector('label');
                    if (label) {
                        var t = (label.textContent || '').trim();
                        var n = parseFloat(t);
                        if (!isNaN(n) && n > 1) price = t;
                    }
                }
                out.push(name + '|||' + price);
            }
            return out;
        """) as? List<String> ?: return

        for (item in results) {
            val parts = item.split("|||")
            if (parts.isEmpty()) continue
            val name = parts[0]
            if (name.isBlank()) continue
            val price = parts.getOrNull(1)?.toDoubleOrNull()
            if (!into.containsKey(name)) {
                into[name] = price
            } else if (into[name] == null && price != null) {
                into[name] = price
            }
        }
    } catch (e: Exception) {
        // Soft-fail: missed snapshots are recovered by subsequent scroll passes.
    }
}
