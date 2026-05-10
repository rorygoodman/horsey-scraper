---
status: draft
date: 2026-05-09
topic: Multi-market lay-price output schema
---

# Multi-market lay-price output schema

## Goal

Reshape the scraper's `data.json` output so it captures the **best available lay price** on the Betfair Exchange for **multiple markets per race** (Win, Top 2, Top 3, Top 4, Top 5 Finish), pivoted per horse, so the file can be diffed directly against bookmaker E/W odds for arbitrage candidates.

## Non-goals

- No back prices, no stake sizes, no price ladders. Lay-best only.
- No time-series. One snapshot per run, overwriting `data.json`.
- No bookmaker-side scraping. That data comes from a separate source.
- No "To Be Placed" market. Top-N markets are scraped explicitly so we can compare against any bookmaker E/W terms.

## Markets in scope

Per race, scrape five markets:

- `WIN`
- `TOP_2`
- `TOP_3`
- `TOP_4`
- `TOP_5`

Discovery: navigate from each race's Win market page (already known from the race-list scraper) and follow the on-page related-markets links to the four Top-N markets. URL patterns are not assumed to be derivable.

## Output schema (`data.json`)

```json
{
  "scrapedAt": "2026-05-09T12:00:00Z",
  "raceCount": 23,
  "races": [
    {
      "raceId": "1.249508314",
      "venue": "Lingfield",
      "country": "GB",
      "offTime": "2026-05-09T13:30:00+01:00",
      "winMarketUrl": "https://www.betfair.com/exchange/plus/en/horse-racing/market/1.249508314",
      "marketName": "13:30 Lingfield - 5f Hcap",
      "marketScrapedAt": {
        "WIN":   "2026-05-09T12:00:04Z",
        "TOP_2": "2026-05-09T12:00:08Z",
        "TOP_3": "2026-05-09T12:00:11Z",
        "TOP_4": "2026-05-09T12:00:14Z",
        "TOP_5": "2026-05-09T12:00:17Z"
      },
      "runners": [
        {
          "name": "Some Horse",
          "lay": { "WIN": 4.8, "TOP_2": 2.5, "TOP_3": 1.7, "TOP_4": 1.4, "TOP_5": 1.2 }
        },
        {
          "name": "Outsider Bob",
          "lay": { "WIN": 22.0, "TOP_2": 9.5, "TOP_3": 5.0, "TOP_4": 3.2, "TOP_5": 2.4 }
        }
      ]
    }
  ]
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `scrapedAt` (top level) | string, ISO-8601 UTC `Z` | `Instant.now()` at run start |
| `raceCount` | int | Equals `races.length`. (Per rule 7, races with no successful Win scrape are omitted.) |
| `races[].raceId` | string | Betfair stable ID parsed from the Win market URL (the `1.NNN` segment) |
| `races[].venue` | string | As shown on Betfair race list, must be in `Venues.ALL` |
| `races[].country` | string | `"GB"` or `"IE"` from `Venues.countryFor(...)` |
| `races[].offTime` | string, ISO-8601 with offset | Constructed from today's date (Europe/London) + `HH:mm` from race list |
| `races[].winMarketUrl` | string | The Betfair Exchange URL for the Win market (carried through from the race-list scraper, useful for debugging) |
| `races[].marketName` | string | Format: `"<HH:mm> <venue> - <race type>"` (e.g. `"13:30 Lingfield - 5f Hcap"`). Time + venue come from the race-list scrape. Race type comes from `<span class="market-name">` on the Win market page. The `" - <race type>"` suffix is omitted if the span is missing. (We tried `<h1>` first; it was empty on every race in our 2026-05-10 smoke run.) |
| `races[].marketScrapedAt` | object | Map of market type → ISO-8601 UTC `Z` instant. **Only contains keys for markets that were scraped successfully.** |
| `races[].runners[].name` | string | Horse name as shown on Betfair Win market page (source of truth for runner list) |
| `races[].runners[].lay` | object | Map of market type → best lay price as decimal odds. **Same keys as `marketScrapedAt`.** Value is `null` if scraped but no lay was on offer. |

### Edge-case rules

These are normative — they define what is and isn't a valid output file.

1. **Successful market scrape** → key present in `marketScrapedAt`; same key present in every runner's `lay` map (value may be `null`).
2. **Failed market scrape** (timeout, error, page didn't render) → key **omitted** from `marketScrapedAt`; key **omitted** from every runner's `lay` map.
3. **Market doesn't exist** for the race (e.g. `TOP_5` for a 6-runner race; related-markets sidebar doesn't surface it) → treated identically to a failed scrape: key omitted everywhere.
4. **No lay on offer for a runner in a market we scraped** → key present, value `null`.
5. **Phantom horse** (appears in a Top-N market but not in the Win market) → **drop the horse from output** and emit a warning to stderr including race ID and horse name. Win market is the source of truth for the runner list.
6. **Non-runners / withdrawn** → not included in `runners[]`. (Inherited rule: if Betfair removes them from the runner list, so do we.)
7. **Race with zero successfully-scraped markets** → race object is **omitted entirely** from `races[]` and not counted in `raceCount`. A failure to scrape Win means we have no runner list, so the race entry would be empty.
8. **Race with Win scraped but all Top-N failed** → race is included; `marketScrapedAt` and every `lay` map contain only the `WIN` key.

The unifying principle: **presence of a key means "we scraped this market and observed nothing more on offer"; absence of a key means "we don't know."** Arb code can rely on this distinction.

## Code structure

### `Models.kt` (rewritten)

```kotlin
enum class MarketType { WIN, TOP_2, TOP_3, TOP_4, TOP_5 }

data class Race(
    val raceId: String,        // "1.249508314"
    val venue: String,
    val country: String,       // "GB" | "IE"
    val offTime: String,       // ISO-8601 with Europe/London offset
    val winMarketUrl: String
)

data class RunnerOdds(
    val name: String,
    val lay: Map<MarketType, Double?>
)

data class RaceOdds(
    val race: Race,
    val marketName: String,
    val marketScrapedAt: Map<MarketType, String>,  // ISO-8601 UTC
    val runners: List<RunnerOdds>
)
```

The race-list scraper continues to return `List<Race>`; only the field names change (`url` → `winMarketUrl`, plus new `raceId` and full `offTime`).

### `BetfairRaceScraper`

Per race, the scraper:

1. Opens **one** Chrome session.
2. Navigates to the Win market URL.
3. Extracts runners + best lay (existing logic).
4. Extracts `marketName` from `<h1>`.
5. Discovers related-market URLs for `TOP_2`/`TOP_3`/`TOP_4`/`TOP_5` from the in-page navigation (sidebar / dropdown — exact selector TBD during implementation; see "Open implementation questions" below).
6. For each Top-N URL that exists: navigate, wait for runners, extract lay-by-name; merge into the per-runner `lay` map keyed by `MarketType`.
7. Close the browser; return `RaceOdds`.

Failure of any single Top-N market is caught locally and produces "key omitted" semantics; only a Win-market failure causes the whole race to be dropped.

### `Main.kt`

Same single-pass loop. Top-level `scrapedAt` is `Instant.now().toString()`. Polite delays:

- Between races: keep current 2 s.
- Between markets within a race: 500 ms (no DNS / no fresh browser, so smaller is fine).

## Open implementation questions

These are not blocking on the schema, but will need answers during the implementation plan:

- **Related-markets DOM**: how exactly does the Betfair race page expose links to Top 2 / Top 3 / Top 4 / Top 5 Finish? Sidebar, dropdown, tabs? Any markets only available behind a click? Will require a short spike on a real race page (probably in a `DebugMarketLinks.kt` entry-point file).
- **Race off-time on the boundary of midnight UTC**: the current race list returns `HH:mm` only and assumes "today (Europe/London)". For races just after midnight local time scraped just before, the date assumption could be off by one day. Decide whether to handle this (probably yes) or document as known-issue.
- **Re-using a browser across races**: out of scope here, but worth noting as a follow-up.

## Testing

The scraper itself can't be unit-tested without the live Betfair page, and the existing codebase has no tests. Verification for this change is two-pronged:

- **Schema validation**: a small offline check that loads the produced `data.json` and asserts the rules in "Edge-case rules" hold (key parity between `marketScrapedAt` and each runner's `lay`, ISO-8601 format on every timestamp, `raceId` regex, `country ∈ {GB, IE}`). Can be a Kotlin entry-point or a Python/jq script — to be decided at plan time.
- **Manual spot-check**: after a real run, eyeball one race and confirm the lay prices match what the Betfair UI is showing for Win + Top 2/3/4/5.

## Migration

This is a breaking change to the JSON shape. There are no documented downstream consumers of `data.json` yet, so no migration plan is required — overwrite at next run.

## Acceptance

A run completes and produces a `data.json` such that, for at least one race:

- The top-level shape matches the schema above.
- `marketScrapedAt` contains five keys (`WIN`, `TOP_2`, `TOP_3`, `TOP_4`, `TOP_5`).
- Every runner has a `lay` map with the same five keys.
- All `scrapedAt` values are valid ISO-8601 UTC instants.
- `offTime` is a valid ISO-8601 string with a `+00:00` or `+01:00` offset.
- `raceId` matches the regex `^1\.\d+$`.

For a race where some Top-N markets don't exist: `marketScrapedAt` and each runner's `lay` map contain only the keys that were successfully scraped.

A phantom horse seen during scraping produces a stderr warning of the form `Phantom horse '<name>' in <market> for race <raceId> — dropping`.
