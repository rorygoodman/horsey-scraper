---
status: draft
date: 2026-07-31
topic: Novibet scraper — third bookie, novibethorses.json, arb_finder generalisation
---

# Novibet scraper

## Goal

Add **Novibet** as a third bookie alongside PaddyPower and 888sport. Scrape
every Novibet race for the selected regions that runs today, with full win
prices and each-way terms, into a new `novibet.json`. Price each-way arbs
against the shared Betfair lay scrape into a new `novibethorses.json`, and
wire that file into the published web page's existing source toggle.

Along the way, collapse `arb_finder`'s per-bookie duplication into a single
generic path — the refactor the 888sport spec deferred with "if a third
bookie ever lands, revisit".

## Motivation

Novibet is a third independent book. Its prices and each-way terms are its
own, so a third set of arbs comes off the same Betfair lay scrape at
near-zero marginal cost.

It is also the point where `arb_finder`'s copy-per-bookie shape stops
paying. Two bookies did not justify an abstraction; three do. Adding
Novibet without it would mean a third near-identical price leg, horse
model, rename map, output writer and CLI branch.

## Non-goals

- **Not** a full generic bookie abstraction. The three scraper packages
  stay independent — they wrap genuinely different APIs, and their
  duplication is shallow. Only `arb_finder` is unified.
- **Not** extracting a shared `browser.py`. Novibet gets a third
  near-identical copy. This is the most obvious remaining duplication and
  is flagged as the next cleanup, but it is out of scope here.
- **Not** the standalone place-market arb (see Opportunities below).
- **Not** a combined cross-bookie view on the web page. Novibet becomes a
  third entry in the existing source toggle, nothing more.
- **Not** changing `horses.json` or `888horses.json`. The `arb_finder`
  refactor is required to leave both byte-identical.

## The data source (investigated + confirmed 2026-07-31)

Two endpoints on `https://www.novibet.ie`, mirroring 888's
schedule/racecard split. `4324` is the horse-racing sport id and `4372612`
the `HORSE_RACING` marketViewGroupId; both are constants.

### Auth

A bare `curl` — even with every header from a real browser session — gets a
**Cloudflare 403** (`Attention Required! | Cloudflare`). A headless-Chromium
warmup GET on `https://www.novibet.ie/sports/horse-racing/4372612` followed
by an in-page `fetch()` returns **200**. This is exactly the `BrowserSession`
pattern both existing scrapers use, verified working against the live site.

The in-page fetch must carry the `x-gw-*` header set; unlike 888's
`fetch_json` (which sends only `accept`), these headers are load-bearing:

```
x-gw-domain-key: _IE          x-gw-cms-key: _IE
x-gw-application-name: NoviIE  x-gw-currency-sysname: EUR
x-gw-country-sysname: IE       x-gw-language-sysname: en-IE
x-gw-client-timezone: Europe/Dublin
x-gw-channel: WebPC            x-gw-client-layout: Desktop
x-gw-odds-representation: Fractional
```

Shared query string: `?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE`.

### 1. Day index

```
GET /spt/feed/marketviews/horse-racing-overview2/4324/4372612
```

Returns `days[]` (today **and tomorrow** — filter to today) → `countries[]`
→ `meetings[]` → `races[]`:

- `countries[].caption`: precise country code — `GB`, `IRE`, `USA`, `AUS`,
  `SAF`, `GER`. Notably better than 888's coarse `uk-and-ireland`.
- `meetings[].caption`: venue (e.g. `"Goodwood"`); `meetings[].path` its slug.
- `races[]`: `betContextId`, `startTimeUTC` (ISO `+00:00`), `timeStr`
  (local), `runnersCount`, `status` (all upcoming races observed as
  `Dormant`).

Sample: today's index held **49 GB/IRE races**.

### 2. Racecard

```
GET /spt/feed/marketviews/horse-racing-race2/4324/<betContextId>
```

Relevant fields:

- `startDateTime` (ISO `+00:00`), `title`, `runners` (count).
- `horses[]`: `horseName`, `horseStatus` (`Runner` / `NonRunner`),
  `teamBetCode`. Non-runners are dropped.
- `marketCategories[]`, each with `sysname`, `caption`, and
  `items[].betViews[].betItems[]` carrying `caption` (runner name),
  `price` (decimal), `oddsText` (fractional), `isAvailable`.

Categories observed across a 12-race GB sample:

| Category sysname | Meaning | Used |
|---|---|---|
| `HORSE_RACING_MAIN` | Race Winner — win prices | ✅ 12/12 |
| `HORSE_RACING_RACE_WINNER_EACHWAY_<P>_<D>` | each-way terms — **read the caption, not the sysname** | ✅ 12/12 |
| `HORSE_RACING_RACE_PLACE_<N>` | standalone place market | ❌ (see Opportunities) |
| `HORSE_RACING_RACE_INSURANCE_<N>` | Insurebet | ❌ |
| `HORSE_RACING_RACE_STRAIGHT_FORECAST` | Forecast | ❌ |

**Each-way terms** appear as a single market category per race, carrying
both a sysname (`HORSE_RACING_RACE_WINNER_EACHWAY_3_5`) and a caption
(`"E/W 1/5 - 3 Places"`). The sysname *looks* like `<places>_<divisor>`.
(The nested `marketSysname` is the literal template string
`HORSE_RACING_RACE_WINNER_EACHWAY_P_D` — the numbers live only on the
category sysname.)

**The sysname is not trustworthy, and the caption is authoritative.**
Across 30 GB/IRE races scanned on 2026-07-31: 22 agreed, **5 disagreed**,
3 had no each-way market. Every disagreement was a `Place Boost` race,
where the sysname retains the *base* terms while the caption advertises the
*boosted* terms actually on offer:

```
sysname 3_4  ->  caption "Place Boost 1/5 - 4 Places"   (x4)
sysname 2_5  ->  caption "Place Boost 1/5 - 5 Places"   (x1)
```

Some Place Boost races *do* agree, so "is it a boost?" is not a usable
discriminator either — the caption must simply be the source of truth.

This matters because both failure modes bias the same way. Pricing the
`3_4` race off its sysname gives a place fraction of 1/4 instead of 1/5
*and* compares against Betfair's `TOP_3` lay instead of `TOP_4` — each
error inflates the computed edge, so the scraper would report arbs that do
not exist.

**Parsing rule:** extract terms from the caption with
`1/(\d+)\s*-\s*(\d+)\s*Places?`, which covers both the `E/W` and
`Place Boost` prefixes (19 and 8 of the 30 races respectively). An
unparseable caption never falls back to the sysname and is never guessed —
the race is kept with `eachWayTerms: null` and a warning on stderr (see
Error handling below).

The each-way category's prices are identical to the win market's, as
expected: an each-way bet is struck at the win price with the terms
applied. Win prices are therefore taken from `HORSE_RACING_MAIN` and the
each-way category is read for its terms only.

## Components

New package `src/novibet_scraper/`, mirroring `sport888_scraper/`:

- `api.py` — endpoint constants, warmup URL, racecard URL builder, the
  `x-gw-*` header set, User-Agent. No I/O.
- `browser.py` — headless-Chromium session: warmup GET, then
  `fetch_json(url)` sending the `x-gw-*` headers. Third copy of the
  pattern (see Non-goals).
- `regions.py` — region id → Novibet country captions:
  `gb-ie → {GB, IRE}`, `us → {USA}`. Novibet's taxonomy is its own, so
  this map lives with the scraper, as 888's does.
- `overview.py` — parse the day index into race stubs (`bet_context_id`,
  venue, country caption, `off_time`, `runners_count`), filtered to today
  and the selected regions.
- `racecard.py` — parse a racecard into runners (name, win price, raw
  fractional price) plus `EachWayTerms` read from the each-way category's
  **caption** (see the data-source section), dropping non-runners.
- `models.py` — `NovibetRace`, `NovibetRunner`, `EachWayTerms`,
  `NovibetOutput`. snake_case internally, snake→camel on output.
- `output.py` — serialize to `novibet.json`.
- `validation.py` + `validate.py` — schema validator + CLI.
- `cli.py` + `__main__.py` — `python -m novibet_scraper [regions]`.

Filtering follows the same day/off-race window convention as the other two
scrapers, for consistency.

## `arb_finder` unification

Landed as **its own commit, green, before Novibet touches `arb_finder`** —
so the refactor is verified in isolation against the existing golden tests.

- `models.py` — replace `PaddyPriceLeg` and `Sport888PriceLeg` with one
  `BookiePriceLeg` (win_price, win_price_raw, each_way_terms), and
  `Horse`/`Horse888` with one `PricedHorse`. The two hand-written rename
  maps collapse into one built per bookie; the leg key (`paddypower` /
  `sport888` / `novibet`) and the `<bookie>ScrapedAt` field are the only
  variables.
- `calculator.py` — one `find_horses_by_name(betfair, bookie_output, bookie)`
  serving both 888 and Novibet. `find_horses` stays as-is: PaddyPower joins
  on Betfair ids, which is a genuinely different join, not a parameter.
- `cli.py` — `--source {paddypower,888,novibet}` becomes table-driven
  (source → input file, output file, parser, leg name) instead of an
  if/else chain. Default stays `paddypower`, so bare `python -m arb_finder`
  is unchanged.

**Safety property: `horses.json` and `888horses.json` must come out
byte-identical.** `test_horses_golden.py` and the 888 equivalents are what
prove it; both run before and after the refactor commit.

## The join

Novibet carries no Betfair ids, so it reuses `arb_finder/matching.py`
unchanged — race matched on off-time instant plus normalized venue
(with the single-race-at-instant fallback), runner matched on exact
normalized name. No fuzzy matching: a wrong match is a silently mispriced
arb.

Novibet's times are `+00:00` like 888's. `venue`, `country`, `off_time`
and the Betfair ids on each output row come from the **matched Betfair**
race, so `country` lands as precise `GB`/`IE` regardless of Novibet's own
`IRE`/`USA` captions. Unmatched races and runners are counted and reported,
never guessed.

## Output schemas

### `novibet.json`

The complete Novibet card — every winner-market runner for the selected
regions today, deliberately *not* filtered to Betfair-matchable races, so
unmatched runners stay visible. Mirrors `888sport.json`:

```
{
  "scrapedAt": "...Z",
  "raceCount": N,
  "races": [
    {
      "venue": "Goodwood",
      "country": "GB",
      "offTime": "2026-07-31T13:00:00+00:00",
      "marketName": "Race Winner",
      "scrapedAt": "...Z",
      "eachWayTerms": { "fraction": 0.2, "places": 3 },
      "runners": [
        { "name": "Rajiba", "winPrice": 2.75, "winPriceRaw": "7/4" }
      ]
    }
  ]
}
```

### `novibethorses.json`

Same shape and edge/sort semantics as `888horses.json`, with the bookie leg
keyed `novibet`. Only matched, fully-priced runners; sorted by `edge`
descending.

## Pipeline wiring

`run.sh` gains two **non-fatal** stages, guarded exactly as the 888 stages
are — a Novibet outage must never block the PaddyPower publish:

```
uv run python -m novibet_scraper "$REGIONS" || echo "..." >&2
uv run python -m arb_finder --source novibet || echo "..." >&2
```

`publish.sh` pushes `novibethorses.json` when present, alongside
`888horses.json`. `index.html` gains one `SOURCES` entry
(`novibet: { file: "novibethorses.json", leg: "novibet", label: "NB" }`) —
the map is already generic. `.gitignore` gains both new outputs.

## Error handling

Follows the existing scrapers' conventions:

- Index fetch failure → exit 1 (catastrophic).
- Per-race fetch/parse failure → skip that race, count it, continue; exit 1
  only if *every* attempted race failed.
- Unparseable each-way caption → **the race is not skipped.** It stays in
  `novibet.json` with `eachWayTerms: null`, and a warning naming the
  offending caption is printed to stderr (not a silent mispricing, not a
  whole-run failure). This keeps `novibet.json` the complete card per race,
  matching the "not filtered to Betfair-matchable races" contract in the
  output-schema section above. The stderr warning is the signal to watch
  for a caption-format change — `find_horses_by_name` already skips any
  runner whose race has `eachWayTerms: null`, so a parse failure here can
  only cost coverage, never mis-price an arb.
- Legitimate empty day → write empty `novibet.json`, exit 0.
- Arb step: missing/invalid inputs → exit 2; success (even zero horses) → 0.

## Testing

TDD, unit tests per module against fixtures captured from the live feed on
2026-07-31 and committed under `tests/fixtures/` (day index plus eight
racecards; see `tests/fixtures/novibet_README.md` for what each one
exercises). Heaviest coverage on:

- each-way **caption** parsing across both prefixes (`E/W …`,
  `Place Boost …`) and all of 2/3/4/5/6 places;
- the two boost-mismatch fixtures, asserting the parsed terms follow the
  caption and *not* the sysname — the regression that would otherwise
  manufacture phantom arbs;
- races with no each-way market, with markets already pulled near the off,
  and with `marketCategories: []` → skipped and counted;
- non-runner exclusion via `horseStatus`;
- region/country mapping, including `IRE`→matched-Betfair-`IE`;
- today-only filtering when the index carries tomorrow's day too;
- the `arb_finder` golden tests, proving `horses.json` and
  `888horses.json` are unchanged by the refactor.

Plus schema-validity guards for the two new files and an opt-in
(`RUN_INTEGRATION=1`) live test, like the other two scrapers.

## Known limitations

- **Six-place races are unpriceable.** `top_n_from_places` maps only 2–5,
  because Betfair's to-be-placed markets stop at `TOP_5`. Novibet ran
  6-place boosts on **3 of the 30** GB/IRE races scanned (~10%), so this
  is not a corner case. Such races match on Betfair but produce no priced
  horses; `arb_finder`'s `MatchStats.races_unpriceable` counts them
  separately from plain "matched" races so the run summary doesn't overstate
  coverage — the same behaviour PaddyPower already has, just more frequent
  here. Not fixable
  without Betfair data that does not exist.
- **The `.ie` domain** (EUR, `usrGrp=IE`) is used, per the captured
  session. Its index covers GB/IRE/USA, and GB-race prices are assumed to
  match `novibet.co.uk`. Unverified; switching domains is a constant change
  in `api.py` if it ever matters.

## Opportunities (deliberately deferred)

Novibet exposes **standalone place markets** (`HORSE_RACING_RACE_PLACE_2`,
`_3`) with independently-priced place odds — e.g. one sampled race showed
implied each-way fractions of 0.24–0.37 *across runners in the same race*,
because these are priced per-runner rather than derived from a fixed
fraction. That enables a **place-only arb** against Betfair's `TOP_N` lay
that the current each-way frame cannot express, and it is real edge sitting
unused. It needs its own edge formula, output shape and page treatment, so
it belongs in its own spec rather than bolted onto this one.

## Risks

- **Venue-name drift** between Novibet and Betfair is the main matching
  risk, as it was for 888. The off-time-instant fallback mitigates it and
  unmatched races are logged.
- **Cloudflare** may tighten. The warmup is verified working today; if it
  starts failing, the non-fatal `run.sh` guard means only Novibet output is
  lost.
- **Caption format change** for each-way terms would break parsing. Since
  the caption is the only trustworthy source (the sysname is demonstrably
  wrong on Place Boost races), there is no fallback by design: an
  unparseable caption is never guessed, and the race is kept with
  `eachWayTerms: null` rather than skipped (see Error handling above). The
  signal to watch for a format change is the per-caption stderr warning,
  plus the "without each-way terms" count in the scraper's own summary line
  and the `races_unpriceable` count `arb_finder` prints when it runs against
  Novibet — a format change would show up as a jump in both rather than as
  silently wrong prices.
- **The `arb_finder` refactor** touches code that currently ships correct
  output for two bookies. Mitigated by landing it as a standalone green
  commit guarded by golden tests.
