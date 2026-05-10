package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.JavascriptExecutor
import org.openqa.selenium.WebDriver
import java.time.LocalDate
import java.time.ZoneId

private val LONDON = ZoneId.of("Europe/London")

/**
 * Assembles [Race]s from raw "venue|||hhmm|||href" lines. Pure: no DOM, no
 * clock. Filters out unknown venues, lines with no parseable race ID, and
 * lines with unparseable times. Dedupes by raceId and sorts by offTime
 * then venue.
 *
 * If `countryOverride` is non-null, every race gets that country directly,
 * bypassing the [Venues] lookup. This is used for single-country tabs
 * (e.g. the US tab) where tab membership is itself proof of country.
 *
 * If `countryOverride` is null (default), country is resolved per venue via
 * [Venues.countryFor] and unknown venues are skipped with a warning. This
 * is the path for the GB+IE tab where the two countries are mixed.
 */
fun assembleRaces(
    rawLines: List<String>,
    today: LocalDate,
    zone: ZoneId,
    countryOverride: String? = null
): List<Race> {
    val races = rawLines.mapNotNull { line ->
        val parts = line.split("|||")
        if (parts.size != 3) return@mapNotNull null
        val (venue, hhmm, href) = Triple(parts[0], parts[1], parts[2])
        val country = countryOverride ?: Venues.countryFor(venue) ?: run {
            System.err.println("Skipping unknown venue: '$venue' ($hhmm)")
            return@mapNotNull null
        }
        val raceId = extractRaceId(href) ?: return@mapNotNull null
        val offTime = buildOffTime(hhmm, today, zone) ?: return@mapNotNull null
        Race(raceId = raceId, venue = venue, country = country, offTime = offTime, winMarketUrl = href)
    }
    return races.distinctBy { it.raceId }.sortedWith(compareBy({ it.offTime }, { it.venue }))
}

/**
 * Scrapes the Betfair Exchange "Today's Racing" landing page for the GB & IE
 * meetings shown on the default tab.
 *
 * DOM shape (as of 2026-05):
 *   ul.country-tabs-container
 *     li.country-tab.active     <-- GB & IE tab is default-active
 *   div.country-content
 *     li.meeting-item
 *       .meeting-info .meeting-label          <-- venue ("Southwell")
 *       ul.race-list li.race-information
 *         a.race-link[href="horse-racing/market/1.NNN"]
 *           span.label                         <-- HH:mm
 */
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7"
) {
    fun scrape(): List<Race> {
        val driver: WebDriver = createChromeDriver()
        try {
            driver.get(url)
            val js = driver as JavascriptExecutor
            val ready = waitForMeetings(driver)
            if (!ready) {
                dumpDiagnostics(js)
                return emptyList()
            }

            ensureGbIeTabActive(driver)
            Thread.sleep(800)
            val raw = extractRawMeetings(js)
            return assembleRaces(raw, LocalDate.now(LONDON), LONDON)
        } finally {
            driver.quit()
        }
    }

    private fun waitForMeetings(driver: WebDriver): Boolean {
        val deadline = System.currentTimeMillis() + 30_000L
        while (System.currentTimeMillis() < deadline) {
            val n = driver.findElements(By.cssSelector("li.meeting-item")).size
            if (n > 0) {
                Thread.sleep(700)
                return true
            }
            Thread.sleep(500)
        }
        return false
    }

    private fun dumpDiagnostics(js: JavascriptExecutor) {
        try {
            val info = js.executeScript("""
                return JSON.stringify({
                    title: document.title,
                    url: location.href,
                    bodyLen: (document.body && document.body.innerText || '').length,
                    meetingItems: document.querySelectorAll('li.meeting-item').length,
                    raceLinks: document.querySelectorAll('a.race-link').length,
                    countryTabs: document.querySelectorAll('li.country-tab').length,
                    activeTab: (document.querySelector('li.country-tab.active .country-label') || {}).textContent || ''
                });
            """) as String
            System.err.println("List page diagnostics: $info")
        } catch (e: Exception) {
            System.err.println("Diagnostics failed: ${e.message}")
        }
    }

    private fun ensureGbIeTabActive(driver: WebDriver) {
        try {
            val tabs = driver.findElements(By.cssSelector("li.country-tab"))
            for (tab in tabs) {
                val flagsHtml = tab.getAttribute("innerHTML") ?: ""
                if (flagsHtml.contains("country-flags-gb") && flagsHtml.contains("country-flags-ie")) {
                    val classAttr = tab.getAttribute("class") ?: ""
                    if (!classAttr.contains("active")) {
                        tab.click()
                        Thread.sleep(700)
                    }
                    return
                }
            }
        } catch (e: Exception) {
            // Tab structure may differ when only one country has races.
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun extractRawMeetings(js: JavascriptExecutor): List<String> {
        return js.executeScript("""
            var out = [];
            var meetings = document.querySelectorAll('li.meeting-item');
            for (var i = 0; i < meetings.length; i++) {
                var meetingEl = meetings[i];
                var labelEl = meetingEl.querySelector('.meeting-label');
                if (!labelEl) continue;
                var venue = (labelEl.textContent || '').trim();
                if (!venue) continue;

                var raceLinks = meetingEl.querySelectorAll('a.race-link');
                for (var r = 0; r < raceLinks.length; r++) {
                    var a = raceLinks[r];
                    var labelSpan = a.querySelector('span.label');
                    var time = labelSpan ? (labelSpan.textContent || '').trim()
                                         : (a.textContent || '').trim();
                    var timeMatch = time.match(/\d{1,2}:\d{2}/);
                    if (!timeMatch) continue;
                    out.push(venue + '|||' + timeMatch[0] + '|||' + a.href);
                }
            }
            return out;
        """) as? List<String> ?: emptyList()
    }
}
