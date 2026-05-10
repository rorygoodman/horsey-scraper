package com.horsey.scraper

import org.openqa.selenium.By
import org.openqa.selenium.WebDriver
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

private const val TOP_N_TYPES_COUNT = 4
private const val INTER_MARKET_DELAY_MS = 500L

private val HHMM = DateTimeFormatter.ofPattern("HH:mm")

/**
 * Pure formatter for the per-race `marketName` output field.
 *
 * Combines the local off time + venue (always known) with the race-type
 * snippet scraped from the page (e.g. "5f Hcap", "1m Listed"). Returns
 * `"<HH:mm> <venue> - <raceType>"` when the race-type is present, or just
 * `"<HH:mm> <venue>"` as a fallback.
 */
fun formatMarketName(race: Race, raceType: String): String {
    val time = OffsetDateTime.parse(race.offTime).format(HHMM)
    val trimmed = raceType.trim()
    return if (trimmed.isEmpty()) "$time ${race.venue}"
           else "$time ${race.venue} - $trimmed"
}

/**
 * Pure assembler: combines a [Race], a market name, and a per-market scrape
 * map into a [RaceOdds] for output. Returns null when the WIN scrape is
 * absent (per spec rule 7: race with no Win is omitted).
 */
fun assembleRaceOdds(
    race: Race,
    marketName: String,
    scrapes: Map<MarketType, MarketScrape>
): RaceOdds? {
    if (MarketType.WIN !in scrapes) return null

    val orderedTypes = MarketType.values().filter { it in scrapes }
    val marketScrapedAt = linkedMapOf<MarketType, String>()
    for (type in orderedTypes) {
        marketScrapedAt[type] = scrapes.getValue(type).scrapedAt
    }
    val runners = pivotMarketScrapes(scrapes, raceIdForWarnings = race.raceId)

    return RaceOdds(
        raceId = race.raceId,
        venue = race.venue,
        country = race.country,
        offTime = race.offTime,
        winMarketUrl = race.winMarketUrl,
        marketName = marketName,
        marketScrapedAt = marketScrapedAt,
        runners = runners
    )
}

/**
 * Scrapes one race across WIN + Top 2/3/4/5 Finish in a single Chrome
 * session. Returns null if the Win scrape failed (per spec rule 7).
 *
 * Failures of individual Top-N markets are caught and produce key-omitted
 * semantics in the output (per spec rules 2 & 3).
 */
class BetfairRaceScraper(private val race: Race) {
    fun scrape(): RaceOdds? {
        val driver: WebDriver = createChromeDriver()
        try {
            driver.get(race.winMarketUrl)

            val winScrape = try {
                scrapeLoadedMarket(driver, MarketType.WIN)
            } catch (e: Exception) {
                System.err.println("WIN scrape failed for ${race.raceId}: ${e.message}")
                return null
            }

            val marketName = extractMarketName(driver)
            val scrapes = linkedMapOf(MarketType.WIN to winScrape)

            val topNUrls = try {
                findTopNUrls(driver)
            } catch (e: Exception) {
                System.err.println("Related-markets discovery failed for ${race.raceId}: ${e.message}")
                emptyMap<MarketType, String>()
            }

            for (type in listOf(MarketType.TOP_2, MarketType.TOP_3, MarketType.TOP_4, MarketType.TOP_5)) {
                val url = topNUrls[type] ?: continue  // market not present on page
                Thread.sleep(INTER_MARKET_DELAY_MS)
                try {
                    driver.get(url)
                    scrapes[type] = scrapeLoadedMarket(driver, type)
                } catch (e: Exception) {
                    System.err.println("$type scrape failed for ${race.raceId}: ${e.message}")
                    // Key omitted: do not put into `scrapes`.
                }
            }

            check(scrapes.size <= 1 + TOP_N_TYPES_COUNT) { "more market types than expected" }
            return assembleRaceOdds(race, marketName, scrapes)
        } finally {
            driver.quit()
        }
    }

    private fun extractMarketName(driver: WebDriver): String {
        // Betfair race pages expose the race type (e.g. "5f Hcap", "1m Listed")
        // in <span class="market-name">. The page's <h1> turns out to be empty
        // on every race we've seen, so we don't use it. Time + venue we already
        // know from the race-list scrape; combine them with the race type to
        // produce the spec format "<HH:mm> <venue> - <race type>".
        val raceType = try {
            driver.findElement(By.cssSelector("span.market-name")).text
        } catch (e: Exception) {
            ""
        }
        return formatMarketName(race, raceType)
    }
}
