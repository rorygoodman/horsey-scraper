---
status: draft
date: 2026-05-26
topic: PaddyPower scraper — rewrite in Python, meetings-driven, full today coverage
---

# PaddyPower scraper — Python rewrite

## Goal

Replace the Kotlin `next-races` PaddyPower scraper with a standalone
Python CLI that pulls **every PaddyPower race for the selected regions
that runs today (Europe/London)**, with full WIN-market data (runners,
prices, each-way terms, Betfair exchange market id). Output goes to
the same `paddypower.json` file the existing arb finder already
consumes — schema unchanged, downstream Kotlin untouched.

## Motivation

The current scraper hits a single `content-managed-page/v7` endpoint
with a hardcoded card id, which is the API behind PaddyPower's
"next races" widget. Two practical limitations have surfaced:

1. **Tomorrow leakage.** When the day's UK card winds down, the
   widget rolls forward to tomorrow's Irish evening races. In the
   most recent run, 7 of 9 PP races returned were tomorrow's; only 2
   joined to today's Betfair scrape.
2. **Per-card cap.** The widget tops out around 19 races globally;
   most of today's GB+IE card is invisible to it.
3. **Stale card id.** The hardcoded id (`19424`) drifts — the
   live page is currently using `21149`+`18030`. Today's
   useful coverage is whatever those rotating cards happen to expose.

The `?tab=meetings-results` view is backed by a different endpoint
combination that exposes the day's full meeting index and per-meeting
markets. Migrating to that source lifts coverage from ~2 today GB+IE
races to ~18 in the recent run, without the tomorrow leakage.

Separately: PaddyPower is a JS-heavy Cloudflare-gated site; the
scraper needs headless Chromium either way. Doing this in Python
removes ~3s of JVM boot per run, makes Playwright iteration faster,
and is friendlier to vibe-coding. The remaining pipeline
(Betfair + arb) stays in Kotlin; integration is via the existing
`paddypower.json` file boundary, so the language split adds no new
coupling beyond a JSON contract.

## Non-goals

- Not changing the `paddypower.json` schema. The arb finder, schema
  validator, and Kotlin model dataclasses (`PaddyOutput`,
  `PaddyRace`, etc.) keep their current shape and consume the
  Python output unmodified.
- Not changing the Betfair scraper or arb finder. They remain
  Kotlin and read/write the same files.
- Not rewriting Kotlin into Python wholesale. Only the PaddyPower
  *scraper* (the parts that hit PP's API and parse its response)
  is moving languages. The Python module knows nothing about
  Betfair or arb.
- No login, no auth, no account. PaddyPower endpoints are open;
  Cloudflare is the only gate.
- No retries on per-meeting fetch failure. Failed meetings are
  logged and skipped; partial output is acceptable.
- No concurrency. Per-meeting fetches run sequentially in one browser
  context. A run for GB+IE is 1 + ~5-8 HTTP calls, well under a
  minute; concurrency would complicate Cloudflare cookie handling
  for no real win.

## Prerequisites

One-time setup (documented in `paddypower-py/README.md`):

```
# Install uv (macOS: brew; other OSes: install script)
brew install uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync --project paddypower-py                              # creates .venv, installs deps
uv run --project paddypower-py playwright install chromium   # ~150MB browser binary
```

Python `>=3.11` (for `zoneinfo` and modern type hints). `uv` handles
the interpreter and venv. The Playwright Chromium binary lives in the
shared Playwright cache directory and may already be present from
the Kotlin Playwright install — `playwright install chromium` is a
no-op if so.

## Architecture overview

### Data flow

```
                        run.sh
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       Kotlin Betfair       Python paddypower_scraper
       (gradlew run)              (uv run)
              │                         │
              ▼                         ▼
        betfair.json              paddypower.json
              │                         │
              └────────────┬────────────┘
                           ▼
                   Kotlin ArbMain
                    (gradlew run)
                           │
                           ▼
                       arbs.json
```

### Runtime flow inside the Python scraper

1. **Parse args.** Single positional region arg (`gb-ie`, `us`, or
   `gb-ie,us`), default `gb-ie`. Capture `run_start_utc` for the
   top-level `scrapedAt`.
2. **Launch headless Chromium via Playwright.** Set UA / locale
   `en-GB` / timezone `Europe/London`. Navigate to
   `https://www.paddypower.com/horse-racing` to earn `cf_clearance`.
   Wait `DOMContentLoaded`.
3. **Fetch the meetings index** with an in-page `fetch()`:
   `content-managed-page/v7?cardsToFetch=63&...` (full URL pinned
   in `api.py`, captured from probe). Parse JSON:
   `attachments.races` → metadata-only list of ~446 races spanning
   3 days, every country PP supports. Each carries `raceId`,
   `meetingId`, `winMarketId`, `startTime` (UTC), `countryCode`,
   `venue`.
4. **Filter** to today's London-day window and the requested
   region's country codes.
5. **Group** survivors by `meetingId` (typically 3-8 meetings for
   GB+IE; ~5-15 for `gb-ie,us`).
6. **Per-meeting fan-out (sequential).** For each meeting, in-page
   `fetch()` `racing-page/v7?raceId=<any-raceId-from-meeting>`.
   Response contains every race in that meeting at top level
   (`races`, `markets`) with the full WIN market: `runners[…]` with
   `selectionId`, `runnerStatus`, `winRunnerOdds.trueOdds.{decimalOdds,
   fractionalOdds}`, plus `eachwayAvailable`, `numberOfPlaces`,
   `placeFraction`, `exchangeMarketId`.
7. **Parse + assemble `PaddyRace` records.** Same drop rules as the
   Kotlin parser today: synthetic runners filtered, price-parity
   enforced, non-runners kept with null prices, UTC converted to
   Europe/London ISO-8601 offset.
8. **On per-meeting failure** (fetch error, parse error, or empty
   result): log `paddy: skipping meeting <id> <venue>: <reason>` to
   stderr, continue.
9. **Write `paddypower.json`** at repo root. Exit 0 whenever the
   file was written (even with zero races — see exit-code table
   for why). Exit 1 only on catastrophic failure (browser launch,
   index fetch, or every-attempted-meeting failed). Exit 2 on bad
   args.

### HTTP budget

- 1 warmup page load (HTML + assets).
- 1 meetings index fetch (~108KB JSON).
- N per-meeting fetches (~150-350KB each), N = number of meetings
  surviving the region + today-window filter. Typical N for
  `gb-ie`: 3-8.

Total wall time: ~10-20s including browser boot. Comparable to the
current Kotlin next-races scraper.

## Project layout

```
horsey-scraper/
├── paddypower-py/                      # NEW
│   ├── pyproject.toml
│   ├── uv.lock                         # committed
│   ├── README.md                       # setup + local run
│   ├── src/paddypower_scraper/
│   │   ├── __init__.py
│   │   ├── __main__.py                 # `python -m paddypower_scraper`
│   │   ├── cli.py                      # arg parse + orchestration
│   │   ├── browser.py                  # Playwright session + in-page fetch helper
│   │   ├── api.py                      # URL builders + constants
│   │   ├── meetings.py                 # parse card-63 → list[RaceStub]
│   │   ├── races.py                    # parse racing-page/v7 → list[PaddyRace]
│   │   ├── models.py                   # dataclasses mirroring paddypower.json
│   │   ├── filtering.py                # london_day_window, region→countries
│   │   └── output.py                   # write_paddypower_json()
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/
│       │   ├── card63_meetings.json    # captured from probe (sanitised)
│       │   └── racing_page_meeting.json
│       ├── test_api.py
│       ├── test_meetings.py
│       ├── test_races.py
│       ├── test_filtering.py
│       ├── test_output.py
│       ├── test_cli.py
│       └── test_browser_smoke.py       # opt-in integration
└── … (existing Kotlin tree, modified)
```

### `pyproject.toml`

```toml
[project]
name = "paddypower-scraper"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["playwright>=1.42"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
paddypower-scraper = "paddypower_scraper.cli:main"
```

### `.gitignore` additions

```
paddypower-py/.venv/
paddypower-py/.pytest_cache/
paddypower-py/**/__pycache__/
paddypower-py/src/**/__pycache__/
```

## Module design

Dependency graph (no cycles, one direction):

```
cli ─┬─→ browser
     ├─→ api
     ├─→ meetings ──→ models
     ├─→ races    ──→ models
     ├─→ filtering ─→ models
     └─→ output  ───→ models
```

### `models.py`

Frozen dataclasses mirroring `paddypower.json` exactly. snake_case
field names; the snake→camel conversion happens once, in `output.py`.

```python
@dataclass(frozen=True)
class EachWayTerms:
    fraction: float
    places: int

@dataclass(frozen=True)
class PaddyRunner:
    name: str
    selection_id: int | None
    win_price: float | None
    win_price_raw: str | None

@dataclass(frozen=True)
class PaddyRace:
    venue: str
    country: str
    off_time: str
    market_name: str
    race_url: str
    scraped_at: str
    betfair_win_market_id: str | None
    each_way_terms: EachWayTerms | None
    runners: list[PaddyRunner]

@dataclass(frozen=True)
class PaddyOutput:
    scraped_at: str
    race_count: int
    races: list[PaddyRace]

@dataclass(frozen=True)
class RaceStub:                          # internal, not in JSON output
    race_id: str
    meeting_id: str
    win_market_id: str
    start_time_utc: str
    country_code: str
    venue: str
```

### `api.py`

URL constants and builders. No I/O.

```python
USER_AGENT  = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
LOCALE      = "en-GB"
TIMEZONE    = "Europe/Dublin"           # PP's regional context

WARMUP_URL  = "https://www.paddypower.com/horse-racing"

MEETINGS_INDEX_URL = (
    "https://apisms.paddypower.com/smspp/content-managed-page/v7"
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl"
    "&cardsToFetch=63&countryCode=IE&currencyCode=EUR&eventTypeId=7"
    "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false"
    "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true"
    "&language=en&layoutFetchedCardsOnly=true&loggedIn=false"
    "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE"
    "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY"
    "&timezone=Europe%2FDublin"
)

def racing_page_url(race_id: str) -> str: ...
```

### `browser.py`

Playwright lifecycle. Synchronous (fan-out is sequential; async
overhead not justified).

```python
class BrowserFetchError(Exception):
    def __init__(self, url: str, reason: str): ...

class BrowserSession:
    """Context manager. Warms up once on __enter__, reuses the same
    browser context (and cf_clearance cookie) for every fetch_json."""

    def __init__(self, *, headless: bool = True): ...
    def __enter__(self) -> "BrowserSession": ...
    def __exit__(self, *exc) -> None: ...

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        """Calls `url` via in-page fetch(), parses JSON.
        Raises BrowserFetchError on non-2xx / eval failure / bad JSON."""
```

### `meetings.py`

Pure parser for the card-63 response.

```python
def parse_meetings_index(payload: dict) -> list[RaceStub]:
    """Walks payload['attachments']['races']. Drops entries missing
    any of: raceId, meetingId, winMarketId, startTime, countryCode,
    venue. Returns RaceStub list."""
```

### `races.py`

Pure parser for the `racing-page/v7` per-meeting response.

```python
def parse_meeting_response(
    payload: dict,
    scraped_at_utc: str,
) -> list[PaddyRace]:
    """Iterates payload['races']. Skips entries where winMarketId is
    null (exchange-history rows). Looks up each race's WIN market in
    payload['markets']. Returns list of PaddyRace."""

_SYNTHETIC_RUNNER_NAMES = frozenset({
    "Unnamed Favourite", "Unnamed 2nd Favourite", "The Field",
})

def _parse_runners(market: dict) -> list[PaddyRunner]: ...
def _parse_eachway(market: dict) -> EachWayTerms | None: ...
def _utc_to_london(iso_utc: str) -> str | None: ...
def _market_name(off_time_london: str, venue: str, race_type: str) -> str: ...
```

### `filtering.py`

Pure time/region math.

```python
REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us":    frozenset({"US"}),
}

def parse_regions(arg: str) -> frozenset[str]: ...
def london_day_window(now_utc: datetime) -> tuple[datetime, datetime]: ...
def in_window(start_time_utc: str, window: tuple[datetime, datetime]) -> bool: ...
```

### `output.py`

```python
_SNAKE_TO_CAMEL = {
    "each_way_terms": "eachWayTerms",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "betfair_win_market_id": "betfairWinMarketId",
    "off_time": "offTime",
    "market_name": "marketName",
    "race_url": "raceUrl",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}

def write_paddypower_json(out: PaddyOutput, path: Path) -> None:
    """Dataclass tree → camelCase dict → JSON. Written atomically
    via path.with_suffix('.tmp') + os.replace."""
```

### `cli.py`

```python
def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], ContextManager[BrowserSession]] = BrowserSession,
    out_path: Path = Path("paddypower.json"),
) -> int:
    """Orchestrates the run. Returns exit code.
    `now_utc` and `make_session` are injectable for testing."""
```

### `__main__.py`

```python
from .cli import main
raise SystemExit(main())
```

## Behaviour

### Today-window semantics

`london_day_window(now_utc) -> (start_utc, end_utc)`:

- `start_utc = now_utc`
- `end_utc = midnight of *tomorrow* in Europe/London, converted to UTC`
  (exclusive)

A race passes when `start_utc <= race.start_time_utc < end_utc`.
Races already off (start_time before now) still pass — the arb finder
decides what to do with in-running races, mirroring current Kotlin
behaviour.

### Two response shapes (the gotcha)

| Endpoint | Where races/markets live |
|---|---|
| `content-managed-page/v7?cardsToFetch=63` | `payload["attachments"]["races"]`, `…["markets"]` |
| `racing-page/v7?raceId=...`               | `payload["races"]`, `payload["markets"]` (top-level) |

`meetings.py` and `races.py` each own their shape. Crossing them
produces an immediate `KeyError` rather than silently empty output.

### Race drop rules

A race is **dropped silently** if:
- `winMarketId` is null (exchange-history row in `racing-page/v7`).
- Its WIN market is missing from `payload["markets"]`.
- After runner filtering, `len(runners) == 0`.

A race is **dropped with a stderr log** if:
- `countryCode` is missing or blank (can't safely region-filter).

A runner is **dropped silently** if its name is in
`_SYNTHETIC_RUNNER_NAMES`.

A runner is **kept with `win_price` and `win_price_raw` both null** if:
- `runnerStatus != "ACTIVE"` (non-runner / withdrawn).
- `winRunnerOdds.trueOdds` is missing or malformed (parity invariant).

### Failed meeting

Any of: `BrowserFetchError`, JSON decode error, exception inside
`parse_meeting_response`, OR zero usable races after drop rules.
Each logs one line:

```
paddy: skipping meeting <meetingId> <venue>: <reason>
```

Pipeline continues. Counter increments.

### `scrapedAt` timestamps

- **Top-level `scrapedAt`** = `run_start_utc`, captured once at the
  start of `main()`. Same value for the entire output.
- **Per-race `scrapedAt`** = the UTC instant captured just before
  the meeting's `racing-page/v7` fetch was issued. **All races in
  the same meeting share that single timestamp** (one fetch returns
  the whole meeting). Different meetings → different per-race
  timestamps. The schema validator already permits this; the
  Kotlin scraper happens to write one value because it makes one
  call, not because the schema requires it.

### Output JSON shape

`output.py` walks the dataclass tree and emits camelCase keys using
`_SNAKE_TO_CAMEL`. Python `None` → JSON `null`. Field order matches
existing `paddypower.json`. Written atomically (`paddypower.json.tmp`
+ `os.replace`) — defends against the arb finder reading a partial
file if anything ever runs them concurrently.

### Browser session reuse

One `BrowserSession` per run. Warmup hits `/horse-racing` once →
earns the `cf_clearance` cookie → that single browser context reuses
it for the index call and all per-meeting calls. The cookie
comfortably outlives a few-minute scrape (Cloudflare's default
clearance lifetime is 30 minutes; our worst-case run is under two).

### Region argument

`parse_regions("gb-ie,us")` → `frozenset({"GB", "IE", "US"})`.
Unknown region id → `ValueError("regions must be non-empty; valid:
gb-ie,us, got: 'xx'")`. `cli.py` catches and exits with code 2
(POSIX misuse convention), error to stderr.

### Logging conventions

- **stdout** — one line at start, per-meeting progress, one summary
  line at end:

  ```
  Fetching PaddyPower meetings for regions=gb-ie...
    18:00 Ballinrobe (35646567) → 13 runners, eachway=1/5 places=3
    18:30 Plumpton   (35646582) → 9 runners, eachway=1/5 places=3
    …
  Wrote paddypower.json (18 races from 5 meetings, 0 skipped)
  ```

- **stderr** — every drop/skip with reason.

Matches the existing Kotlin Betfair scraper's stdout tone so the
`run.sh` log reads uniformly.

### Exit codes

| Code | Condition |
|---|---|
| 0    | Wrote `paddypower.json`. Includes three sub-cases: (a) full success, (b) partial success (≥1 meeting fanned out succeeded, some failed and were logged), (c) **legitimate empty day** — index fetch succeeded but zero meetings matched region + today-window filters. In case (c) the output is `{"scrapedAt": "...", "raceCount": 0, "races": []}` and ArbMain handles it as "no PP coverage today". |
| 1    | Browser launch failed, OR index fetch failed, OR every meeting that was *attempted* failed (i.e. ≥1 meeting matched the filters but none returned usable data). Distinguishes a real fetch problem from a quiet day. |
| 2    | Bad CLI args (unknown region id, empty arg) |

## Integration with existing pipeline

### `run.sh`

Current:

```bash
#!/usr/bin/env bash
set -euo pipefail
./gradlew run --quiet --args="${1:-gb-ie}"
exec ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt
```

Becomes:

```bash
#!/usr/bin/env bash
set -euo pipefail
REGIONS="${1:-gb-ie}"
./gradlew run --quiet --args="$REGIONS"
uv --project paddypower-py run python -m paddypower_scraper "$REGIONS"
exec ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt
```

`set -e` still halts the chain on any non-zero exit — same semantics
as today.

### Kotlin changes

**Delete** the scraper pieces:
- `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`
- `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`
- `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt`

**Keep** the model + validator (still consumed by ArbCalculator and
useful as a contract gate for the Python output):
- `PaddyModels.kt` — `PaddyOutput`/`PaddyRace`/etc. used by ArbCalculator
- `PaddySchemaValidator.kt`
- `PaddyValidateMain.kt`
- Their tests

**Edit `Main.kt`:** remove the "PaddyPower phase" block at the
bottom (current lines 113-128). After Betfair writes `betfair.json`,
Kotlin exits cleanly. `run.sh` is the sole pipeline orchestrator.

**Edit `Regions.kt`:** no change. Python mirrors the table.

## Testing strategy

Test runner: `uv run pytest`. Layout under
`paddypower-py/tests/` mirrors `src/paddypower_scraper/`.

### Test-per-module

| Module | Test file | Approach |
|---|---|---|
| `models.py` | — | Dataclasses with no logic; covered via `test_output.py`. |
| `api.py` | `test_api.py` | Assert `MEETINGS_INDEX_URL` contains required query params; `racing_page_url("35646567.1800")` round-trips with race id intact. |
| `meetings.py` | `test_meetings.py` | Load `fixtures/card63_meetings.json` → assert correct stub count; mutate fixture to drop required fields → assert filtered; empty `attachments.races` → empty list. |
| `races.py` | `test_races.py` | Load `fixtures/racing_page_meeting.json` → assert race count (rows with non-null `winMarketId`); exchange-history skipped; synthetic runners dropped; `REMOVED` runner kept with null prices; price-parity via mutated fixture; market without `eachwayAvailable=true` → `each_way_terms is None`; `_utc_to_london` covers BST + GMT; `_market_name` with and without race_type. |
| `filtering.py` | `test_filtering.py` | `parse_regions` happy + bad + empty; `london_day_window` for BST + GMT; `in_window` boundary at end (exclusive) and at `now` (inclusive). |
| `output.py` | `test_output.py` | Build `PaddyOutput` → write → read back → assert camelCase keys, nested shape matches existing `paddypower.json`; assert no `.tmp` file left behind on success. |
| `browser.py` | `test_browser_smoke.py` | One opt-in integration test (`@pytest.mark.integration`, skipped unless `RUN_INTEGRATION=1`) that launches a real `BrowserSession`, calls `fetch_json(MEETINGS_INDEX_URL)`, asserts dict with `attachments` key. |
| `cli.py` | `test_cli.py` | Inject a `FakeSession` returning canned dicts from a per-URL map. Covers: happy path, partial-meeting-failure, all-meetings-fail (exit 1), index-fetch-fail (exit 1), bad regions arg (exit 2), region filtering, today-window filtering with frozen `now_utc`. No real browser. |

### Fixture provenance

- `card63_meetings.json` — captured from a probe run on 2026-05-26
  (the 132KB content-managed-page response with
  `cardsToFetch=63`). Sanitised: keep `attachments.races` +
  `attachments.meetings` + `attachments.eventTypes`; drop the rest.
- `racing_page_meeting.json` — the 351KB Ballinrobe dump from the
  per-race probe. Sanitised similarly; keeps top-level `races` +
  `markets` only.
- Synthetic mutations (no-eachway, malformed odds, missing required
  field) built in `conftest.py` helpers via `copy.deepcopy` +
  targeted mutation. Keeps the surface honest without committing
  near-duplicate JSON files.

### Cross-language contract test

One opt-in test in `test_output.py` (marked `@pytest.mark.contract`,
run via `RUN_CONTRACT=1`) writes a representative `PaddyOutput` to a
temp file and shells out to the existing Kotlin validator:

```
./gradlew run --quiet \
  -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt \
  --args="<tmpfile>"
```

Exit code 0 = the Python output is byte-shape compatible with what
the arb finder expects. Slow (~15s gradle boot) so opt-in. This is
the test that actually guards the language boundary; worth running
before merging schema-related changes.

### What we don't test

- Live PaddyPower fetches in unit tests (flaky, network-dependent,
  region-blocked in CI).
- 100% line coverage on `cli.py` argparse / logging — focus coverage
  on parsers and filtering.
- Internals of `models.py` dataclasses (no logic).

### Iteration loop

- Inner: `uv run pytest tests/test_races.py -k eachway -x`
- Pre-commit: `uv run pytest`
- Pre-merge: `RUN_INTEGRATION=1 uv run pytest -m integration` and
  `RUN_CONTRACT=1 uv run pytest -m contract`

## Open questions / future work

- **US region.** PaddyPower carries US racing (card 63 returned 134
  US races in the probe). `parse_regions("us")` will fan out US
  meetings the same way; no extra design needed but no live
  verification done yet — confirm in implementation. Existing
  `Regions.kt` already supports US.
- **Concurrent per-meeting fetches.** Current design is sequential.
  If runtime becomes a concern (>30s), introduce a small
  `asyncio.gather` over meetings using Playwright's async API.
  Out of scope for v1.
- **Card-63 id rotation.** Card 63 has been "all meetings" for as
  long as we've observed. If PaddyPower rotates it, the index call
  will return an empty `attachments.races`, the scraper will write
  `paddypower.json` with `raceCount: 0`, and exit 0 (legitimate-empty
  case, per the exit-code table). That output is
  indistinguishable from a genuine no-racing day; the operator
  notices when several days in a row are empty. Recovery is
  "re-probe the page layout and pin a new id" — single-line change
  in `api.py`.
- **Cloudflare hardening.** If PaddyPower stiffens its bot detection,
  the in-page `fetch()` trick may start failing. Fallback options:
  click-through navigation per meeting (slower, but uses real
  user interactions), or stealth-mode Playwright plugins.
- **Per-bookmaker reuse.** The eventual second-bookmaker scraper
  (Bet365, William Hill) can copy this module's shape — same
  `paddypower.json`-style output file per bookmaker, same arb
  consumer pattern.

## Appendix: PaddyPower endpoint surface (as of 2026-05-26)

### Meetings index — `content-managed-page/v7` with `cardsToFetch=63`

Returns ~446 races spanning today + next 2 days, all countries
PaddyPower supports (GB, IE, US, FR, JP, CL, AU, AR, BR, HK, ZA, IT,
NZ, etc.). Race entries have metadata only — no prices, no runners,
no each-way terms. Each race carries:

```
raceId         "35646567.1800"
meetingId      "35646567"
winMarketId    "927.385112402"
winMarketName  "2m Hcap Hrd"
startTime      "2026-05-26T18:00:00.000Z"  (UTC)
countryCode    "IE"
venue          "Ballinrobe"
```

### Per-meeting — `racing-page/v7?raceId=<any-race-in-meeting>`

Returns the whole meeting (every race) plus every market for those
races at top level (`races`, `markets`), not under `attachments`.
One call per meeting yields full WIN market data for every race in
that meeting.

WIN market fields the parser consumes:

```
exchangeMarketId    "1.258556270"        ← Betfair join key
eachwayAvailable    true
numberOfPlaces      3
placeFraction       {numerator: 1, denominator: 5}
runners[].runnerName
runners[].selectionId
runners[].runnerStatus           ("ACTIVE" | "REMOVED")
runners[].winRunnerOdds.trueOdds.decimalOdds.decimalOdds
runners[].winRunnerOdds.trueOdds.fractionalOdds.{numerator, denominator}
```

The response also includes ancillary markets (`"Money Back if 2nd"`,
specials, etc.) — the parser ignores everything except the
WIN market identified by each race's `winMarketId`.

### Cloudflare warmup

`https://www.paddypower.com/horse-racing` page load drops a
`cf_clearance` cookie scoped to `*.paddypower.com`. Subsequent
in-page `fetch()` calls against `apisms.paddypower.com` reuse it via
`credentials: 'include'`. The cookie's lifetime is many minutes —
ample for a sub-minute scrape using one browser context.
