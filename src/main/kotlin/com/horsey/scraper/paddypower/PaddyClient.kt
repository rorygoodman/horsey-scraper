package com.horsey.scraper.paddypower

import com.microsoft.playwright.Browser
import com.microsoft.playwright.BrowserType
import com.microsoft.playwright.Playwright
import com.microsoft.playwright.options.LoadState

// URL captured 2026-05-13 — see src/test/resources/paddy-next-races-endpoint.txt.
private const val NEXT_RACES_URL =
    "https://apisms.paddypower.com/smspp/content-managed-page/v7" +
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl" +
    "&cardsToFetch=19424&countryCode=IE&currencyCode=EUR&eventTypeId=7" +
    "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false" +
    "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true" +
    "&language=en&layoutFetchedCardsOnly=true&loggedIn=false" +
    "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE" +
    "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY" +
    "&timezone=Europe%2FDublin"

// Visit the parent page first so Cloudflare drops the cf_clearance cookie
// in the browser session before we hit the API.
private const val WARMUP_URL = "https://www.paddypower.com/horse-racing"

/**
 * Fetches PaddyPower's next-races JSON via a real headless Chromium
 * instance so Cloudflare's bot challenge resolves naturally.
 *
 * Flow:
 *   1. Launch headless Chromium.
 *   2. Visit the public horse-racing landing page; wait for network idle.
 *      This earns the `cf_clearance` cookie scoped to *.paddypower.com.
 *   3. Fetch the JSON endpoint via the in-page `fetch()` API so the
 *      browser's TLS / cookie / fingerprint state carries through.
 *   4. Return the response body as a String.
 *
 * Each call launches and tears down its own browser. For a one-shot CLI
 * that's acceptable (~2-3 s of fixed overhead). If we ever need multiple
 * scrapes per run, hoist the browser into a lifecycle-managed singleton.
 *
 * Prerequisite: the Playwright Chromium binary must be installed once
 * (`./gradlew run -PmainClass=com.microsoft.playwright.CLI --args="install chromium"`
 * or equivalent). Tests don't exercise this class; only live runs do.
 */
class PaddyClient {
    fun getNextRaces(): String {
        Playwright.create().use { pw ->
            val browser: Browser = pw.chromium().launch(
                BrowserType.LaunchOptions().setHeadless(true),
            )
            try {
                val context = browser.newContext(
                    Browser.NewContextOptions()
                        .setUserAgent(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
                            "AppleWebKit/537.36 (KHTML, like Gecko) " +
                            "Chrome/126.0.0.0 Safari/537.36",
                        )
                        .setLocale("en-GB")
                        .setTimezoneId("Europe/Dublin"),
                )
                val page = context.newPage()
                page.navigate(WARMUP_URL)
                page.waitForLoadState(LoadState.NETWORKIDLE)

                // Fetch from inside the page so Cloudflare cookies + TLS fingerprint
                // are used. evaluate() returns the response body.
                val body = page.evaluate(
                    """
                    async (url) => {
                        const r = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: { 'accept': 'application/json, text/plain, */*' },
                        });
                        if (!r.ok) {
                            const text = await r.text();
                            throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 500));
                        }
                        return await r.text();
                    }
                    """.trimIndent(),
                    NEXT_RACES_URL,
                ) as? String

                return body ?: error("PaddyClient: empty response body from $NEXT_RACES_URL")
            } finally {
                browser.close()
            }
        }
    }
}
