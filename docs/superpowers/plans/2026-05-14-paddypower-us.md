# PaddyPower US Racing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing PaddyPower next-races scraper to also fetch a US-targeted URL on every run, so `paddypower.json` contains both GB/IE and US races for the arb finder to join against the Betfair US runners we already scrape.

**Architecture:** `PaddyClient` becomes region-symmetric: it knows two URLs (GB/IE + US), fetches both via the existing Playwright + in-page `fetch()` flow, returns a `List<String>` of JSON response bodies. `PaddyNextRacesFetcher` parses each independently and concatenates the resulting `PaddyRace` lists before applying the existing region filter. No JSON schema change; the same parser handles both responses (verified: same `apisms.paddypower.com` endpoint, only `cardsToFetch=…` differs).

**Tech Stack:** Kotlin 1.9, JDK 17, JUnit 5 via `kotlin("test")`, Gson, Playwright (already on the classpath). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-14-paddypower-us-design.md`

---

## Background for the engineer

If you've never touched this codebase:

- This is a Kotlin/JVM repo that scrapes Betfair (via REST API) and PaddyPower (via Playwright-driven headless Chromium, because PaddyPower's APIs are behind Cloudflare Bot Fight Mode). Outputs are `betfair.json` and `paddypower.json` respectively; a downstream arb finder joins them into `arbs.json`. All four files are produced by a single `./run.sh` invocation.
- The existing PaddyPower scraper hits one URL: `apisms.paddypower.com/smspp/content-managed-page/v7?...cardsToFetch=19424...` (the "Extra Place Races" card, GB/IE-only). You're adding a second URL for US racing.
- The PaddyPower JSON shape is documented in the test class KDoc of `PaddyResponsesTest` and in the spec `docs/superpowers/specs/2026-05-13-paddypower-scraper-design.md`. The US response uses the same shape — verified by the user — so no parser changes are needed.
- The existing `PaddyClient` is a `final` class with a single `getNextRaces(): String` method. Task 1 makes it `open` so tests can subclass with a stub.
- Playwright is already configured; the Chromium binary should already be installed in `~/.cache/ms-playwright/`. If not: `./gradlew run --quiet -PmainClass=com.microsoft.playwright.CLI --args="install chromium"`.
- Test baseline at start of Task 1: 182 tests (verify with `./gradlew test`). Each task adds tests; the plan states the expected new count.

If anything in this background contradicts the actual code at HEAD, trust the code and pause to flag it.

### The Task 0 capture is human-blocking

Task 0 asks the engineer (or a subagent) to discover the US-side PaddyPower endpoint via DevTools, capture the response body as a fixture, and record the URL. PaddyPower's API is behind Cloudflare so automated/headless capture from a script doesn't replay — only a real browser session can produce the response. Same procedure as Task 0 of the original PaddyPower plan.

---

## Task 0: Discover the US endpoint and capture the fixture

**Required outputs (committed):**
- `src/test/resources/paddy-next-races-us-sample.json` — a real response body from PaddyPower's US-racing JSON endpoint.
- `src/test/resources/paddy-next-races-us-endpoint.txt` — a 4-line file listing the endpoint URL, HTTP method, any required headers (e.g. cookies, custom `X-*`), and the date captured.

**This task is human-blocking.** A subagent should *attempt* the discovery via WebFetch first; if WebFetch can't find the endpoint, report **BLOCKED** with a clear message so the human partner can do the DevTools work.

- [ ] **Step 1: Attempt automated discovery via WebFetch**

Fetch `https://www.paddypower.com/horse-racing/us-racing` (if that URL exists) and the main horse-racing landing page. Look in the response for clues:
- Inline `<script>` tags containing URLs matching patterns like `/api/`, `/cms/`, `/sports/`, `/odds/`, or strings like `cardsToFetch`, `usRaces`, `usRacing`.
- Any global JS config (e.g. `window.__INITIAL_STATE__`, `window.PREFETCHED_DATA`) listing card ids.
- Compare against the existing `src/test/resources/paddy-next-races-endpoint.txt` (the GB/IE URL is `https://apisms.paddypower.com/smspp/content-managed-page/v7?...cardsToFetch=19424...`). If you find a similar URL with a different `cardsToFetch=…` value pointing at US races, that's a strong candidate.

Report what you find. Do not invent URLs.

- [ ] **Step 2: Validate any candidate endpoint**

Cloudflare will reject raw `curl` regardless of headers — there's no point trying. Even with cookies from a browser session, the TLS fingerprint mismatches and Cloudflare returns the "Just a moment..." challenge page. If Step 1 surfaced a candidate URL, you cannot validate it server-side; only a real browser can produce the response.

So this step is just: report what you found in Step 1 and let the human partner validate by opening the URL in their browser.

- [ ] **Step 3: Commit fixture and endpoint metadata**

If the human partner provides a captured response body (saved from DevTools → Network → right-click → "Save response as..."):

```bash
mkdir -p src/test/resources
# Move the user's captured file into place. Example:
# mv ~/Downloads/content-managed-page-v7.json src/test/resources/paddy-next-races-us-sample.json
```

Create `src/test/resources/paddy-next-races-us-endpoint.txt` with exactly this format (substitute the real values from the captured cURL):

```
URL: <the full endpoint URL captured>
Method: GET
Headers: real browser request (sec-fetch-*, Origin/Referer https://www.paddypower.com/, Chrome User-Agent). Cookies cf_clearance + __cf_bm are fingerprinted to the original TLS session — Playwright handles these natively for production; do not attempt to replay via raw HTTP.
Captured: <YYYY-MM-DD>
```

Verify the fixture contains race data (look for venue strings + horse names + fractional prices):

```bash
test -f src/test/resources/paddy-next-races-us-sample.json \
  && wc -c src/test/resources/paddy-next-races-us-sample.json \
  && jq '.attachments.races | keys | length' src/test/resources/paddy-next-races-us-sample.json
```

Expected: file exists, several thousand bytes, and the `attachments.races` map has at least one entry.

Commit both files:

```bash
git add src/test/resources/paddy-next-races-us-sample.json \
        src/test/resources/paddy-next-races-us-endpoint.txt
git commit -m "paddy: capture US next-races endpoint fixture"
```

- [ ] **Step 4: If discovery fails — BLOCK**

If Steps 1–2 don't yield a valid URL, report status **BLOCKED** with this exact recipe for the human partner:

> "BLOCKED: Couldn't discover PaddyPower's US next-races JSON endpoint via WebFetch. The human partner needs to do the DevTools work:
> 1. Open the PaddyPower US racing page in Chrome (try `https://www.paddypower.com/horse-racing/us-racing` first; if that 404s, navigate from the main horse-racing page to a US track).
> 2. F12 → Network tab → filter 'Fetch/XHR'.
> 3. Refresh the page.
> 4. Sort by Size (descending). Look for a JSON response containing US race/runner data (US track names like Churchill Downs, Hawthorne, Belmont; horse names; fractional prices).
> 5. Right-click the request → 'Save response as...' → save to `src/test/resources/paddy-next-races-us-sample.json`.
> 6. Right-click → 'Copy as cURL' → paste the URL/method/headers into `src/test/resources/paddy-next-races-us-endpoint.txt`.
> 7. `git add` + commit both files with message `paddy: capture US next-races endpoint fixture`."
>
> Also list everything you tried during automated discovery so the user knows you weren't lazy.

---

## Task 1: PaddyClient — two URLs, `open` class, `List<String>` return

Make `PaddyClient` region-symmetric: it knows both URLs, fetches both, returns one JSON body per URL. Per-URL failures are logged but don't fail the whole call. Total failure (zero URLs succeeded) throws. The class becomes `open` (and its method `open`) so tests in Task 2 can subclass.

The signature change (`getNextRaces(): String` → `List<String>`) breaks `PaddyNextRacesFetcher`. Update both files in this single commit so the compile stays clean.

**Files:**
- Modify: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`

- [ ] **Step 1: Read the captured US URL**

Run: `cat src/test/resources/paddy-next-races-us-endpoint.txt`

Note the URL on the first line. You'll paste it into `PaddyClient.kt` as the `NEXT_RACES_URL_US` constant. If the file doesn't exist or has no real URL, return BLOCKED — Task 0 didn't complete.

- [ ] **Step 2: Replace `PaddyClient.kt`**

Open `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`. Replace the entire file with:

```kotlin
package com.horsey.scraper.paddypower

import com.microsoft.playwright.Browser
import com.microsoft.playwright.BrowserType
import com.microsoft.playwright.Page
import com.microsoft.playwright.Playwright
import com.microsoft.playwright.options.LoadState

// URLs captured via DevTools — see src/test/resources/paddy-next-races-endpoint.txt
// and paddy-next-races-us-endpoint.txt. Replace NEXT_RACES_URL_US with the
// real URL from the metadata file at Task 0 commit time.
private const val NEXT_RACES_URL_GBIE =
    "https://apisms.paddypower.com/smspp/content-managed-page/v7" +
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl" +
    "&cardsToFetch=19424&countryCode=IE&currencyCode=EUR&eventTypeId=7" +
    "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false" +
    "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true" +
    "&language=en&layoutFetchedCardsOnly=true&loggedIn=false" +
    "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE" +
    "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY" +
    "&timezone=Europe%2FDublin"

// PASTE the URL captured in Task 0 here, exactly as written in
// src/test/resources/paddy-next-races-us-endpoint.txt.
private const val NEXT_RACES_URL_US = "<<<PASTE US URL FROM TASK 0 HERE>>>"

private const val WARMUP_URL = "https://www.paddypower.com/horse-racing"

/**
 * Fetches PaddyPower's next-races JSON via a real headless Chromium
 * instance so Cloudflare's bot challenge resolves naturally.
 *
 * Fetches every configured URL (currently GB/IE and US) and returns
 * one JSON response body per URL. Per-URL failures are caught and
 * logged to stderr; the caller receives a list of whichever URLs
 * succeeded. If every URL fails, throws so the caller exits non-zero.
 *
 * Each URL gets its own short-lived browser lifecycle to keep the
 * code simple. Sequential, ~10s per URL — acceptable for a one-shot
 * CLI.
 *
 * `open` so tests can subclass with a stub that bypasses Playwright.
 *
 * Prerequisite: the Playwright Chromium binary must be installed once
 * (`./gradlew run -PmainClass=com.microsoft.playwright.CLI --args="install chromium"`).
 */
open class PaddyClient {

    open fun getNextRaces(): List<String> {
        val urls = listOf(NEXT_RACES_URL_GBIE, NEXT_RACES_URL_US)
        val responses = mutableListOf<String>()
        for (url in urls) {
            try {
                responses += fetchOne(url)
            } catch (e: Exception) {
                System.err.println("paddy: failed to fetch $url: ${e.message}")
            }
        }
        if (responses.isEmpty()) {
            error("PaddyClient: every configured URL failed")
        }
        return responses
    }

    private fun fetchOne(url: String): String {
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
                page.navigate(
                    WARMUP_URL,
                    Page.NavigateOptions().setTimeout(20_000.0),
                )
                page.waitForLoadState(
                    LoadState.DOMCONTENTLOADED,
                    Page.WaitForLoadStateOptions().setTimeout(10_000.0),
                )

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
                    url,
                ) as? String

                return body ?: error("PaddyClient: empty response body from $url")
            } finally {
                browser.close()
            }
        }
    }
}
```

Replace `<<<PASTE US URL FROM TASK 0 HERE>>>` with the real URL on line that the metadata file shows.

- [ ] **Step 3: Update `PaddyNextRacesFetcher.kt` to consume `List<String>`**

Open `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`. Find the existing `fetch` body:

```kotlin
    fun fetch(regions: Set<String>): PaddyOutput {
        val runStart = nowProvider().toString()
        val json = client.getNextRaces()
        val races = parsePaddyNextRaces(json, nowProvider)
        val filtered = filterRacesByCountries(races, Regions.countriesForAll(regions))
        return PaddyOutput(
            scrapedAt = runStart,
            raceCount = filtered.size,
            races = filtered,
        )
    }
```

Replace with:

```kotlin
    fun fetch(regions: Set<String>): PaddyOutput {
        val runStart = nowProvider().toString()
        val responses = client.getNextRaces()
        val races = responses.flatMap { response ->
            try {
                parsePaddyNextRaces(response, nowProvider)
            } catch (e: Exception) {
                System.err.println("paddy: failed to parse response: ${e.message}")
                emptyList()
            }
        }
        val filtered = filterRacesByCountries(races, Regions.countriesForAll(regions))
        return PaddyOutput(
            scrapedAt = runStart,
            raceCount = filtered.size,
            races = filtered,
        )
    }
```

The change: consume `List<String>` instead of `String`; `flatMap` parse over each response with a per-response try/catch so a malformed response doesn't poison the others.

- [ ] **Step 4: Compile**

Run: `./gradlew compileKotlin compileTestKotlin`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: Run the full suite**

Run: `./gradlew test`

Expected: 182 tests pass (same as baseline — no new tests in this task; we're verifying the existing tests still work after the signature/refactor change).

- [ ] **Step 6: Commit**

```bash
git add src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt \
        src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt
git commit -m "paddy: PaddyClient fetches both GB/IE and US URLs; fetcher concatenates"
```

---

## Task 2: New tests for two-response merge behaviour

Add tests that exercise the new "concatenate races from multiple client responses" behaviour. Uses a stub `PaddyClient` subclass (possible because Task 1 made the class `open`).

**Files:**
- Modify: `src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt`

- [ ] **Step 1: Write the failing tests**

Open `src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt`. Add the following before the closing `}` of the existing test class. The snippet uses `java.time.Instant` via fully-qualified names so no new imports are needed; `PaddyOutput`, `PaddyClient`, and `PaddyNextRacesFetcher` are in the same package as the test file.

```kotlin

    @Test
    fun `fetcher concatenates races from multiple client responses`() {
        val gbResponse = synthesisedResponse(country = "GB", venue = "Lingfield")
        val usResponse = synthesisedResponse(country = "US", venue = "Belmont")
        val client = StubPaddyClient(listOf(gbResponse, usResponse))
        val fetcher = PaddyNextRacesFetcher(client) { fixedInstant }
        val output = fetcher.fetch(setOf("gb-ie", "us"))
        assertEquals(2, output.raceCount)
        assertEquals(setOf("GB", "US"), output.races.map { it.country }.toSet())
    }

    @Test
    fun `region filter selects only the requested region's races from the merged list`() {
        val gbResponse = synthesisedResponse(country = "GB", venue = "Lingfield")
        val usResponse = synthesisedResponse(country = "US", venue = "Belmont")
        val client = StubPaddyClient(listOf(gbResponse, usResponse))
        val fetcher = PaddyNextRacesFetcher(client) { fixedInstant }

        val usOnly = fetcher.fetch(setOf("us"))
        assertEquals(1, usOnly.raceCount)
        assertEquals("US", usOnly.races.single().country)

        val gbOnly = fetcher.fetch(setOf("gb-ie"))
        assertEquals(1, gbOnly.raceCount)
        assertEquals("GB", gbOnly.races.single().country)
    }

    @Test
    fun `malformed response is skipped while well-formed responses still contribute`() {
        val malformed = "{ this is not json at all"
        val gbResponse = synthesisedResponse(country = "GB", venue = "Lingfield")
        val client = StubPaddyClient(listOf(malformed, gbResponse))
        val fetcher = PaddyNextRacesFetcher(client) { fixedInstant }
        val output = fetcher.fetch(setOf("gb-ie"))
        assertEquals(1, output.raceCount)
        assertEquals("GB", output.races.single().country)
    }

    // --- helpers ---

    private val fixedInstant: java.time.Instant = java.time.Instant.parse("2026-05-14T12:00:00Z")

    private class StubPaddyClient(private val responses: List<String>) : PaddyClient() {
        override fun getNextRaces(): List<String> = responses
    }

    /**
     * Builds a minimal PaddyPower-shape JSON containing exactly one race
     * with the given country and venue. Mirrors the
     * `attachments.{races, markets}` shape that `parsePaddyNextRaces`
     * expects. Hand-built to keep the test self-contained.
     */
    private fun synthesisedResponse(country: String, venue: String): String = """
        {
          "attachments": {
            "races": {
              "1.fake": {
                "raceId": "1.fake",
                "winMarketId": "m.fake",
                "winMarketName": "5f Hcap",
                "startTime": "2026-05-15T19:00:00.000Z",
                "countryCode": "$country",
                "venue": "$venue"
              }
            },
            "markets": {
              "m.fake": {
                "marketId": "m.fake",
                "raceId": "1.fake",
                "marketType": "WIN",
                "exchangeMarketId": "1.exchange",
                "numberOfPlaces": 3,
                "placeFraction": { "numerator": 1, "denominator": 5 },
                "eachwayAvailable": true,
                "runners": [
                  {
                    "selectionId": 12345,
                    "runnerName": "Test Horse",
                    "runnerStatus": "ACTIVE",
                    "winRunnerOdds": {
                      "trueOdds": {
                        "decimalOdds": { "decimalOdds": 5.0 },
                        "fractionalOdds": { "numerator": 4, "denominator": 1 }
                      }
                    }
                  }
                ]
              }
            }
          }
        }
    """.trimIndent()
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `./gradlew test --tests 'com.horsey.scraper.paddypower.PaddyNextRacesFetcherTest'`

Expected: all tests pass, including the three new ones. If the stub-client tests fail with "PaddyClient is final", you missed making the class `open` in Task 1 — go back and add `open` to both the class header and the `getNextRaces` method signature.

- [ ] **Step 3: Run the full suite**

Run: `./gradlew test`

Expected: 185 tests pass (182 baseline from Task 1 + 3 new in this task).

- [ ] **Step 4: Commit**

```bash
git add src/test/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcherTest.kt
git commit -m "paddy: test two-response merge, region filter, malformed-response skip"
```

---

## Task 3: Final validation

Verification only — no code changes, no commits.

- [ ] **Step 1: Full test run**

Run: `./gradlew test 2>&1 | tail -10`

Expected: `BUILD SUCCESSFUL`. Test total ≈ 185.

- [ ] **Step 2: Compile + assemble**

Run: `./gradlew compileKotlin compileTestKotlin assemble`

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 3: Confirm the US URL is real**

Run: `grep -nE 'PASTE|<<<' src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`

Expected: no output. If the placeholder string is still there, Task 1 Step 2 wasn't completed.

- [ ] **Step 4: Confirm both fixtures exist**

Run: `ls -l src/test/resources/paddy-next-races*.json src/test/resources/paddy-next-races*.txt`

Expected: four files (GB/IE sample + endpoint metadata, US sample + endpoint metadata).

- [ ] **Step 5: Commits added by this plan**

Run: `git log --oneline master..HEAD`

Expected: three commits (Task 0 fixture capture, Task 1 plumbing, Task 2 tests).

- [ ] **Step 6: Surface the live-smoke step to the user**

Don't run a live scrape unattended — it requires the user's existing Betfair credentials at `~/.horsey-scraper/credentials.json` and the Playwright Chromium binary. Tell the user:

> "PaddyPower US scraping merged. To smoke-test live:
>
> 1. Run `./run.sh gb-ie,us`. Expected: takes ~20s longer than before (two PaddyPower fetches instead of one). Produces `betfair.json`, `paddypower.json`, `arbs.json`.
> 2. `jq '[.races[] | .country] | group_by(.) | map({country: .[0], count: length})' paddypower.json`. Expected: shows both `GB`/`IE` and `US` entries.
> 3. `./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args=paddypower.json`. Expected: `paddypower.json: VALID (matches spec)`.
> 4. `./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbValidateMainKt --args=arbs.json`. Expected: `arbs.json: VALID (matches spec)`.
>
> Whether `arbs.json` contains positive-margin US arbs depends on the day's prices."

No commit in this task.

---

## Out-of-scope / follow-ups

These are deliberately not in this plan; mention them to the user when reporting completion:

- **Parallel Playwright launches.** Both URL fetches happen sequentially (~20s total). Could be parallelised but adds complexity for a one-shot CLI.
- **Retry on a failed URL fetch.** If Cloudflare misbehaves, the user re-runs `./run.sh`.
- **Region-specific `cardsToFetch` parameterisation.** Currently two URLs are hardcoded. If PaddyPower adds new card types, that's a separate spec.
- **Browser instance reuse between fetches.** Each URL gets its own browser. Saves ~5s if pooled but adds lifecycle complexity.
- **PaddyPower's potentially-different US response shape.** The spec assumes identical shape; the parser doesn't accommodate divergence. If Task 0 reveals a meaningfully different shape, escalate before continuing.
