package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver
import org.openqa.selenium.WebElement
import org.openqa.selenium.support.ui.ExpectedConditions
import org.openqa.selenium.support.ui.WebDriverWait
import java.time.Duration

/**
 * Scrapes a single Betfair Exchange horse-race win market: pulls the runner
 * names and their best available lay prices.
 *
 * Adapted from the golf-odds-scraper Betfair scraper. Horse races have far
 * fewer runners than golf events, so the virtual-scroll loop usually finishes
 * in one pass — but we keep it for fields with many runners (e.g. ITV7 races).
 */
class BetfairRaceScraper(private val race: Race) {
    private var driver: WebDriver? = null

    fun scrape(): RaceOdds {
        try {
            driver = createChromeDriver()
            driver!!.get(race.url)
            waitForRunners()

            val marketName = extractMarketName()
            val horses = scrollAndExtractHorses()

            return RaceOdds(
                race = race,
                marketName = marketName,
                horses = horses
            )
        } finally {
            driver?.quit()
        }
    }

    private fun waitForRunners() {
        val wait = WebDriverWait(driver!!, Duration.ofSeconds(20))
        wait.until(
            ExpectedConditions.presenceOfElementLocated(By.cssSelector("tr.runner-line, h3.runner-name"))
        )
        Thread.sleep(2000)
    }

    private fun extractMarketName(): String {
        return try {
            driver!!.findElement(By.cssSelector("h1")).text.trim()
                .ifEmpty { "${race.time} ${race.venue}" }
        } catch (e: Exception) {
            "${race.time} ${race.venue}"
        }
    }

    private fun scrollAndExtractHorses(): List<Horse> {
        val js = driver as JavascriptExecutor
        val horsesMap = linkedMapOf<String, Double?>()

        val scrollContainer = findScrollableContainer(js)
        if (scrollContainer == null) {
            collectVisibleHorses(js, horsesMap)
            return horsesMap.map { (name, price) -> Horse(name, price) }
        }

        val clientHeight = js.executeScript("return arguments[0].clientHeight;", scrollContainer) as Long
        js.executeScript("arguments[0].scrollTop = 0;", scrollContainer)
        Thread.sleep(400)

        var noNewCount = 0
        while (noNewCount < 6) {
            val previousSize = horsesMap.size
            collectVisibleHorses(js, horsesMap)
            if (horsesMap.size > previousSize) noNewCount = 0 else noNewCount++

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
                collectVisibleHorses(js, horsesMap)
                break
            }
        }
        return horsesMap.map { (name, price) -> Horse(name, price) }
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

    /**
     * Snapshots currently visible runners. Includes runners with no available
     * lay (price = null) so we know they were in the race even when no money
     * is on the lay side.
     */
    @Suppress("UNCHECKED_CAST")
    private fun collectVisibleHorses(js: JavascriptExecutor, horsesMap: MutableMap<String, Double?>) {
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
                if (!horsesMap.containsKey(name)) {
                    horsesMap[name] = price
                } else if (horsesMap[name] == null && price != null) {
                    horsesMap[name] = price
                }
            }
        } catch (e: Exception) {
            // Soft-fail: missed snapshots are recovered by subsequent scroll passes.
        }
    }
}
