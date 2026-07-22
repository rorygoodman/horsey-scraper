---
status: draft
date: 2026-07-22
topic: 888sport scraper — second bookie, separate 888horses.json, name+time join to Betfair
---

# 888sport scraper

## Goal

Add **888sport** as a second bookie alongside PaddyPower. Scrape every
888sport race for the selected regions that runs today, with full
WIN-market data (runners, win prices, each-way terms), into a new
`888sport.json`. Then price each-way arbs against the shared Betfair
lay scrape into a new, separate `888horses.json`.

The existing PaddyPower path (`paddypower.json` → `horses.json`) and its
web page are left **completely untouched**.

## Motivation

The pipeline currently prices each-way arbs against a single bookie
(PaddyPower). 888sport is a second book with independent prices and
each-way terms, so a second set of arbs is available from the same
Betfair lay scrape at near-zero marginal cost.

888sport exposes a clean JSON API (the "spectate" sportsbook backend),
so — like PaddyPower — no DOM scraping is needed: a headless-Chromium
warmup establishes session cookies, then `fetch()` calls hit the API.

## Non-goals

- **Not** touching the PaddyPower scraper, `paddypower.json`,
  `horses.json`, the arb finder's existing `find_horses` path, or the
  published web page. This is purely additive.
- **Not** publishing `888horses.json` to the web. It is written locally
  alongside `betfair.json`/`paddypower.json`. Web rendering is a possible
  follow-up.
- **Not** merging the two bookies into a unified `horses.json` or a
  generic bookie abstraction. Two bookies do not justify that refactor
  (YAGNI). If a third bookie ever lands, revisit.

## The data source (investigated + confirmed 2026-07-22)

Two endpoints on `https://spectate-web.888sport.com`. Both require valid
session **cookies** (a warmup GET establishes them); without cookies the
API returns 403. `x-forwarded-for` is **not** required (tested — it makes
no difference). `origin`/`referer: https://www.888sport.com/` and a
desktop `User-Agent` are sent.

### 1. Full-day meetings index

```
GET /spectate/racing/getSchedule/horse-racing?tab=today
```

Returns the whole day grouped by category (region) → tournament
(meeting) → event IDs, plus flat detail maps:

- `schedule.categories[]` → `tournaments{ <date>: [ { id, events:[eventId,...] } ] }`
- `event_details[eventId]`: `id`, `name` (venue, e.g. `"Worcester"`),
  `scheduled_start` (ISO UTC, e.g. `"2026-07-22T12:55:00+00:00"`),
  `category_slug`, `tournament_slug`, `scheduled_date`.
- `categories_details[categoryId]`: `slug` → human region.

Region slugs observed:

| 888 `category_slug` | region |
|---|---|
| `uk-and-ireland`  | GB + IE (combined — 888 does not split GB vs IE) |
| `north-america`   | US (also Canada) |
| `australia`, `international`, `rest-of-europe`, `south-america` | other |

Sample: today's index had **39 GB/IE races across 6 meetings**
(Catterick, Leicester, Lingfield, Naas, Wexford, Worcester).

This supersedes the rolling `.../racingSchedule/.../next-races` endpoint
(a fixed ~21-race global window, no full-day coverage) — the full-day
index is what the scraper uses.

### 2. Per-race racecard

```
GET /spectate/sportsbook-req/getRacecard/<eventId>
```

Relevant fields under `racecard`:

- `each_way_terms[eventId]`: `allow_each_way`, `place_odds_divisor`
  (fraction = `1 / place_odds_divisor`), `places_paid` (number of places).
  Observed: divisor `5` → fraction `0.2`, `places_paid` `3`. When
  `allow_each_way != "1"` (win-only race), emit no each-way terms; such
  races are then unpriceable and skipped by the arb step, exactly as the
  PaddyPower path handles `eachWayTerms: null`.
- `selections_details[selId]` filtered to `market_id == "1"` (the
  "Winner Market"): `name`, `decimal_price` (win price), `fraction_price`
  (raw, e.g. `"9/4"`), `active`, `betable`.

888's `eventId`/`selId` are 888's own identifiers — **unrelated to
Betfair market/selection IDs**. This is the crux (see The Join).

## The join — 888 → Betfair (the hard part)

PaddyPower's scraper is Betfair-owned and hands the arb finder Betfair
market + selection IDs, so its join is a trivial ID lookup. 888 gives no
Betfair IDs, so `888horses.json` must join structurally:

1. **Race match.** Match an 888 race to a Betfair race by **off-time
   instant** (parse both to UTC — 888 is `+00:00`, Betfair is `+01:00`
   BST; same instant) **+ normalized venue**. Fallback: if venue names
   disagree but exactly one in-region Betfair race sits at that instant,
   use it. Betfair `country` (GB vs IE) comes from the matched race,
   resolving 888's coarse `uk-and-ireland`.
2. **Runner match.** Within the matched race, match by **normalized
   runner name**: lowercase, strip accents to ASCII, remove punctuation
   (apostrophes/hyphens) and whitespace. **Exact** normalized match only
   — no fuzzy/Levenshtein matching, because a wrong match produces a
   silently mispriced arb.
3. **No match → skip + count.** Any 888 race or runner that does not
   confidently match Betfair is dropped from `888horses.json` and
   reported in the run summary. It is **not** guessed.

Unmatched runners remain fully visible because `888sport.json` is the
**complete** 888 card (see below), so nothing is silently lost — it is
simply not priced.

## Components

New package `sport888_scraper/` (Python identifiers cannot start with a
digit; the output *file* is still `888sport.json`). Mirrors
`paddypower_scraper/`'s module shape:

- `api.py` — endpoint URL builders + constants (warmup URL, the two API
  URLs, User-Agent). No I/O.
- `browser.py` — headless-Chromium session: warmup GET to
  `https://www.888sport.com/horse-racing/` to seed cookies, then
  `fetch_json(url)`. Reuse the PaddyPower `BrowserSession` pattern
  (extract a shared helper only if it falls out cleanly; otherwise a
  small parallel implementation is fine).
- `regions.py` (or a small map in `api.py`) — region id → 888
  `category_slug` (`gb-ie` → `uk-and-ireland`, `us` → `north-america`).
  888's taxonomy differs from `common/regions.py`'s country codes, so
  this map lives with the 888 scraper.
- `schedule.py` — parse `getSchedule` into internal race stubs
  (`event_id`, venue, `category_slug`, `scheduled_start`).
- `racecard.py` — parse `getRacecard` into races + winner-market runners
  + each-way terms.
- `models.py` — `Eight88Race`, `Eight88Runner`, `EachWayTerms`
  (fraction+places), `Eight88Output`. snake_case; snake→camel in output.
- `output.py` — serialize to `888sport.json`.
- `validation.py` + `validate.py` — JSON-schema validator, like the
  others.
- `cli.py` + `__main__.py` — `python -m sport888_scraper [regions]`.

Filtering: same day/off-race window convention as PaddyPower, for
consistency (revisit alongside the existing open PP window decision if
in-running coverage is wanted).

## Arb path — additive extension of `arb_finder`

- `arb_finder/matching.py` (new) — the name+time matcher: `normalize_name`,
  `normalize_venue`, `match_race`, `match_runner`. Pure, heavily tested.
- `arb_finder/calculator.py` — add `find_horses_by_name(betfair, eight88)`
  alongside the existing `find_horses`. Reuses `each_way_arb_margin`.
- `arb_finder/models.py` — add an 888 bookie leg + output model:
  `Sport888PriceLeg` (win_price, win_price_raw, each_way_terms) and a
  `Horse888` whose bookie leg is named for 888 (not `paddypower`), so
  `888horses.json` is semantically correct. Reuse `BetfairLayLeg`,
  `Runner`. venue/country/off_time/`betfairWinMarketId`/`selectionId`
  come from the **matched Betfair** race/runner.
- `arb_finder/cli.py` — add a `--source {paddypower,888}` mode
  (default `paddypower`, so the existing invocation
  `python -m arb_finder` is byte-for-byte unchanged). `--source 888`
  reads `betfair.json` + `888sport.json`, validates both, joins via
  `find_horses_by_name`, and writes `888horses.json`. The run summary
  reports races matched/unmatched and runners priced/unmatched.

## Output schemas

### `888sport.json` (the complete 888 card)

Mirrors `paddypower.json` **minus** Betfair IDs (888 has none). It is
intentionally *not* filtered to Betfair-matchable races — it is every
888 winner-market runner for the region today, so unmatched runners stay
visible here.

```
{
  "scrapedAt": "...Z",
  "raceCount": N,
  "races": [
    {
      "venue": "Worcester",
      "country": "uk-and-ireland",       // 888's coarse region slug
      "offTime": "2026-07-22T12:55:00+00:00",
      "marketName": "Winner Market",
      "scrapedAt": "...Z",
      "eachWayTerms": { "fraction": 0.2, "places": 3 },
      "runners": [
        { "name": "Holy Legend", "winPrice": 3.25, "winPriceRaw": "9/4" },
        ...
      ]
    }
  ]
}
```

### `888horses.json` (priced arbs only)

Same shape and edge/sort semantics as `horses.json`, with the bookie leg
named for 888. venue/country/off_time/Betfair IDs are the matched
Betfair race's (so `country` is precise GB/IE/US). Only matched,
fully-priced runners appear; sorted by `edge` descending.

## Pipeline wiring

`run.sh` gains two additive stages after the existing three; Betfair is
shared, PP stages untouched:

```
uv run python -m betfair_scraper   "$REGIONS"   # existing
uv run python -m paddypower_scraper "$REGIONS"   # existing
uv run python -m arb_finder                      # existing → horses.json
uv run python -m sport888_scraper  "$REGIONS"    # NEW → 888sport.json
uv run python -m arb_finder --source 888         # NEW → 888horses.json
```

A failed 888 scrape should not abort the (already-written) PaddyPower
outputs; ordering the new stages last keeps the existing pipeline's exit
semantics intact for the PP path.

`.gitignore` gains `888sport.json` and `888horses.json` (the other JSON
outputs are already ignored). `publish.sh` is **not** changed.

## Error handling

Follows the PaddyPower scraper's conventions:

- Index fetch failure → exit 1 (catastrophic).
- Per-race fetch/parse failure → skip that race, count it, continue;
  exit 1 only if *every* attempted race failed.
- Legitimate empty day → write empty `888sport.json`, exit 0.
- Arb step: missing/invalid input files → exit 2; success (even zero
  horses) → exit 0.

## Testing

TDD, unit tests per module against captured live fixtures (saved
`getSchedule`, GB/IE `getRacecard`, and AUS `getRacecard` samples exist).
Heaviest coverage on `arb_finder/matching.py`:

- exact normalized name match; accents/apostrophes/hyphens/spacing drift;
- venue-name agreement and the single-race-at-instant fallback;
- off-time instant equality across `+00:00` vs `+01:00`;
- no-match runner and no-match race → skipped and counted;
- two races at the same instant at different venues (no cross-match).

Plus schema-validity guard tests for `888sport.json`/`888horses.json`
example files, and an opt-in (`RUN_INTEGRATION=1`) test hitting the live
888 API like the others.

## Open items / risks

- **Venue-name drift** between 888 and Betfair (e.g. suffixes) is the
  main matching risk; the off-time-instant fallback mitigates it, and
  unmatched races are logged for inspection.
- **Cookie/warmup fragility** — if the warmup does not reliably seed the
  session cookie in headless Chromium, the API 403s; verify during
  implementation and capture the minimal required cookie set.
- **`Horse888` vs reusing `Horse`** — a parallel model avoids a
  misleading `paddypower` field name in `888horses.json`; if the small
  duplication grates, a shared generic leg is a later cleanup, not now.
