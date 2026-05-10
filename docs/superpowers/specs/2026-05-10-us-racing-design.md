---
status: draft
date: 2026-05-10
topic: Add US racing alongside GB/IE
---

# Add US racing alongside GB/IE

## Goal

Extend the scraper to also pick up US horse racing in the same `data.json`. A `RegionTab` abstraction lets `BetfairRaceListScraper` iterate a list of tabs (currently `GB+IE` and `US`), activate each, and accumulate races. Per-race scraping (`BetfairRaceScraper`) and the worker pool are unchanged because US race pages expose the same `Top N Finish` markets.

## Non-goals

- No per-race local-timezone metadata (e.g. a `localTime: "13:00 ET"` field). Off-times remain expressed in `Europe/London`, the time Betfair UK displays.
- No other countries (Australia, France, etc.). Adding them later is one more `RegionTab` entry; not in this scope.
- No hardcoded list of US racetracks. The tab membership is the source of truth.
- No changes to `BetfairRaceScraper`, `RaceWorkerPool`, `MarketScraper`, `RelatedMarketsFinder`, or any per-race logic. US race pages already expose `Top 2/3/4/5 Finish` markets identically.
- No CLI knob to select regions. Default is "all configured regions" (GB+IE + US).

## Architecture

### `RegionTab` and the registry

A small data class plus a static list — both inside `BetfairRaceListScraper.kt`:

```kotlin
data class RegionTab(
    val name: String,                   // for logs: "GB+IE", "US"
    val flagsRequired: Set<String>,     // CSS classes on the flag SVG that must all appear in the tab's innerHTML
    val countryOverride: String?,       // non-null → every venue on this tab is this country;
                                        // null → fall back to Venues.countryFor(venue)
)

private val REGION_TABS = listOf(
    RegionTab("GB+IE", setOf("country-flags-gb", "country-flags-ie"), countryOverride = null),
    RegionTab("US",    setOf("country-flags-us"),                     countryOverride = "US"),
)
```

Why `countryOverride` is nullable:
- The GB+IE tab combines two countries; we still need `Venues.countryFor` to disambiguate per venue.
- The US tab is single-country; we trust tab membership and skip the venue lookup. **No US venue allowlist required.**

### `BetfairRaceListScraper.scrape()` — multi-tab loop

The current single-tab path becomes a loop over `REGION_TABS`. Per-region failure is caught so a missing US tab on a no-US-racing day still lets GB+IE proceed.

```kotlin
fun scrape(): List<Race> {
    val driver: WebDriver = createChromeDriver()
    try {
        driver.get(url)
        if (!waitForMeetings(driver)) {
            dumpDiagnostics(driver as JavascriptExecutor)
            return emptyList()
        }
        val today = LocalDate.now(LONDON)
        val all = mutableListOf<Race>()
        for (region in REGION_TABS) {
            try {
                activateTab(driver, region)
                Thread.sleep(800)
                val raw = extractRawMeetings(driver as JavascriptExecutor)
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

private fun activateTab(driver: WebDriver, region: RegionTab) {
    for (tab in driver.findElements(By.cssSelector("li.country-tab"))) {
        val flagsHtml = tab.getAttribute("innerHTML") ?: ""
        if (region.flagsRequired.all { flagsHtml.contains(it) }) {
            val classes = tab.getAttribute("class") ?: ""
            if (!classes.contains("active")) {
                tab.click()
                Thread.sleep(700)
            }
            return
        }
    }
    error("tab for region ${region.name} not found")
}
```

`activateTab` replaces `ensureGbIeTabActive` (more general, parameterised by tab spec).

### `assembleRaces` — gain a `countryOverride` parameter

Existing signature: `assembleRaces(rawLines, today, zone)`. New signature adds a defaulted parameter so every existing test call remains valid:

```kotlin
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
```

When `countryOverride = null` (default; current GB+IE path), behavior is identical to today.

When `countryOverride = "US"`, the venue lookup is skipped — every race gets `country = "US"` regardless of what `Venues.countryFor` would return. Race ID and time validation still apply: a malformed race ID or time still drops the race.

### Validator — one extra allowed country

`SchemaValidator.kt`:

```kotlin
private val ALLOWED_COUNTRIES = setOf("GB", "IE", "US")
```

A new test confirms a race with `country: "US"` validates clean.

### `Venues.kt` — unchanged

Kept exactly as is. Still authoritative for GB-vs-IE disambiguation. Any future country tab decision is whether to add a venue list (use `countryOverride = null`) or trust the tab (use `countryOverride = "<country>"`).

### Off-time / timezone — unchanged

Betfair UK displays US race times in the viewer's local time (`Europe/London`). `buildOffTime("18:00", today, LONDON)` continues to produce `2026-05-10T18:00:00+01:00` for a US race that was actually 1 pm ET. The off-time string remains the literal instant of the off, expressed in London time.

If a future user wants per-race local-timezone metadata, that's a separate field on `Race` / `RaceOdds` and a separate change.

### Main.kt — cosmetic log change

`"Found N UK/IE races today"` becomes `"Found N races today"`. Per-race log lines already include the country. No behavioral change.

### Worker pool, per-race scraper, market scraper, related-markets finder

**Unchanged.** They all operate on `Race` objects opaquely; they don't care which region produced them.

## Behavior contract

| Property | Behavior |
|---|---|
| `country` field values | Now in `{GB, IE, US}` (was `{GB, IE}`). |
| GB/IE behavior | Identical to before this change. Same venues, same disambiguation, same races. |
| US races | Every meeting on the US tab becomes a race with `country = "US"`. No venue allowlist; tab membership is the proof. |
| Race ordering in output | Still sorted by `(offTime, venue)`. UK and US races interleave in the output by off-time. |
| Region failure isolation | A failure scraping the US tab (missing, layout changed, etc.) is caught and logged; GB+IE still completes. |
| `data.json` schema | Same. Only `country` value set expands. |
| Worker pool | Unchanged. Receives a flat `List<Race>` mixing both regions. |
| Per-race scrape | Unchanged. US race pages expose `Top 2/3/4/5 Finish` identically. |

## Testing

Unit tests added to existing files:

In `BetfairRaceListScraperTest.kt`:

```kotlin
@Test
fun `assembleRaces with countryOverride uses it for every venue`() {
    val raw = listOf(
        "Belmont Park|||18:30|||https://www.betfair.com/exchange/plus/horse-racing/market/1.555",
        "Saratoga|||19:00|||https://www.betfair.com/exchange/plus/horse-racing/market/1.556",
    )
    val races = assembleRaces(raw, today, london, countryOverride = "US")
    assertEquals(2, races.size)
    assertEquals(setOf("US"), races.map { it.country }.toSet())
}

@Test
fun `assembleRaces with countryOverride still drops invalid race id`() {
    val raw = listOf("Belmont Park|||18:30|||https://www.betfair.com/exchange/plus/horse-racing")
    assertEquals(emptyList(), assembleRaces(raw, today, london, countryOverride = "US"))
}

@Test
fun `assembleRaces with countryOverride still drops invalid time`() {
    val raw = listOf("Belmont Park|||not-a-time|||https://www.betfair.com/exchange/plus/horse-racing/market/1.555")
    assertEquals(emptyList(), assembleRaces(raw, today, london, countryOverride = "US"))
}

@Test
fun `assembleRaces without countryOverride still uses Venues lookup (regression check)`() {
    val raw = listOf(
        "Lingfield|||13:30|||https://www.betfair.com/exchange/plus/horse-racing/market/1.111",
    )
    val races = assembleRaces(raw, today, london)  // no countryOverride
    assertEquals("GB", races.single().country)
}
```

In `SchemaValidatorTest.kt`:

```kotlin
@Test
fun `accepts country US`() {
    val good = goodJson.replace(""""country": "GB"""", """"country": "US"""")
    assertEquals(emptyList(), validateScrapeOutput(good))
}
```

The activation loop and tab-discovery JS are not unit-tested (browser-dependent). Verified by smoke run.

## Acceptance

- `./gradlew test` passes after the change with all new tests included.
- `./run.sh 3` produces a `data.json` containing both GB/IE races and US races (assuming today has racing in both regions).
- `./gradlew run -PmainClass=com.horsey.scraper.ValidateMainKt --args='data.json'` reports `VALID (matches spec)`.
- US races in `data.json` have `country: "US"` and at least the `WIN` market scraped; for races where Betfair exposes them, `TOP_2`/`TOP_3`/`TOP_4`/`TOP_5` markets are present too.
- A run on a day with no US racing still produces a valid file with GB/IE races (US tab activation failure is logged but doesn't break the run).
- Pre-existing GB+IE behavior is unchanged: same venue list, same disambiguation, same race count for those regions.

## Open implementation questions

- **Confirm flag class.** The pattern across regions has been `country-flags-<iso2-lowercase>` (`gb`, `ie`). The expected US class is `country-flags-us`. If a quick spike during implementation shows a different class, update the `RegionTab` entry. The current `DebugListMain.kt` already dumps tab structure — adapt or copy that approach if needed.
- **Tab order.** US is now first per the user's observation. We don't depend on order — `activateTab` finds tabs by flag class, not position.
- **Midnight UTC boundary.** A US race scheduled at 11pm ET (4am BST next day) scraped just before midnight London time will be dated to "today (Europe/London)" instead of "tomorrow." Pre-existing edge case, not introduced by this change. Documented as a follow-up in `2026-05-09-multi-market-lay-schema-design.md`.
