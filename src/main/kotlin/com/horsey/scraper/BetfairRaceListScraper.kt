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
 * Describes a Betfair country-tab we want to scrape.
 *
 * @param name           For logs: "GB+IE", "US".
 * @param flagsRequired  CSS classes on the flag SVG that must ALL appear in
 *                       the tab's innerHTML for it to be the tab we want.
 * @param countryOverride If non-null, every venue on this tab is treated as
 *                       this country (passed straight through to
 *                       [assembleRaces]). If null, [Venues.countryFor] is
 *                       used to disambiguate (needed for the GB+IE tab).
 */
data class RegionTab(
    val name: String,
    val flagsRequired: Set<String>,
    val countryOverride: String?,
)

internal val REGION_TABS = listOf(
    RegionTab("GB+IE", setOf("country-flags-gb", "country-flags-ie"), countryOverride = null),
    RegionTab("US",    setOf("country-flags-us"),                     countryOverride = "US"),
)

/**
 * Stable user-facing ID for a region. Lower-cased, with `+` replaced by `-`
 * so it's easy to type as a CLI arg. Used by both the CLI parser
 * ([com.horsey.scraper.parseRegions]) and the constructor's `regions`
 * filter to identify tabs.
 */
internal fun RegionTab.regionId(): String = name.lowercase().replace("+", "-")

/**
 * Scrapes the Betfair Exchange "Today's Racing" landing page for meetings
 * across all tabs in [REGION_TABS]. Currently GB+IE and US.
 *
 * DOM shape (as of 2026-05):
 *   ul.country-tabs-container
 *     li.country-tab.active     <-- some tab is default-active; we click each
 *                                   in turn
 *   div.country-content
 *     li.meeting-item
 *       .meeting-info .meeting-label          <-- venue
 *       ul.race-list li.race-information
 *         a.race-link[href="horse-racing/market/1.NNN"]
 *           span.label                         <-- HH:mm
 *
 * Per-region failure (tab missing, layout changed, etc.) is caught and
 * logged; remaining regions still scrape. A region with no races today
 * (empty meeting list after activation) just contributes 0 races, which is
 * fine.
 */
class BetfairRaceListScraper(
    private val url: String = "https://www.betfair.com/exchange/plus/en/horse-racing-betting-7",
    private val regions: Set<String> = REGION_TABS.map { it.regionId() }.toSet(),
) {
    fun scrape(): List<Race> {
        val driver: WebDriver = createChromeDriver()
        try {
            driver.get(url)
            val js = driver as JavascriptExecutor
            if (!waitForMeetings(driver)) {
                dumpDiagnostics(js)
                return emptyList()
            }
            val today = LocalDate.now(LONDON)
            val all = mutableListOf<Race>()
            for (region in REGION_TABS.filter { it.regionId() in regions }) {
                try {
                    activateTab(driver, region)
                    Thread.sleep(800)
                    val raw = extractRawMeetings(js)
                    all += assembleRaces(raw, today, LONDON, region.countryOverride)
                } catch (e: Exception) {
                    System.err.println("Region ${region.name} failed: ${e.message}")
                }
            }
            return all.distinctBy { it.raceId }
                      .sortedWith(compareBy({ it.offTime }, { it.venue }))
        } finally {
            driver.quit()
        }
    }

    /**
     * Waits up to 30s for at least one li.meeting-item to appear (any tab).
     * Returns true on success, false on timeout (caller should dump diagnostics).
     */
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

    /**
     * Finds the tab matching `region`'s flag classes and clicks it if it's
     * not already active. Throws if the tab isn't on the page (e.g. that
     * region has no racing today and the tab is suppressed).
     *
     * Uses a JS-level click rather than `WebElement.click()` so the OneTrust
     * cookie consent banner overlay (`<div class="onetrust-pc-dark-filter">`,
     * which intercepts native pointer events) doesn't block the tab switch.
     */
    private fun activateTab(driver: WebDriver, region: RegionTab) {
        val js = driver as JavascriptExecutor
        for (tab in driver.findElements(By.cssSelector("li.country-tab"))) {
            val flagsHtml = tab.getAttribute("innerHTML") ?: ""
            if (region.flagsRequired.all { flagsHtml.contains(it) }) {
                val classes = tab.getAttribute("class") ?: ""
                if (!classes.contains("active")) {
                    js.executeScript("arguments[0].click();", tab)
                    Thread.sleep(700)
                }
                return
            }
        }
        error("tab for region ${region.name} not found")
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
