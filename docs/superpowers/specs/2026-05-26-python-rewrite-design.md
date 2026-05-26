---
status: draft
date: 2026-05-26
topic: Rewrite the remaining Kotlin app (Betfair scraper + arb finder) in Python; repo becomes pure Python
---

# Python rewrite — Betfair scraper + arb finder

## Goal

Replace the entire Kotlin/Gradle codebase with a single Python project.
The PaddyPower scraper is already Python (`paddypower-py/`); this work
ports the two remaining Kotlin programs — the **Betfair scraper** and
the **arb finder** — to Python, folds the existing PaddyPower scraper
into one consolidated project, and removes the JVM / Gradle / Kotlin
toolchain entirely.

Result: every pipeline step starts in ~50–100 ms instead of paying
JVM + Gradle cold-start (~2–3 s each), and the whole repo is one
language with one venv, one lockfile, and one test command.

## Motivation

The repo is mid-migration. `run.sh` today is:

```
Kotlin Betfair scrape  →  Python PaddyPower scrape  →  Kotlin arb finder
   (gradlew run)             (uv run)                    (gradlew run)
```

Two of three steps still boot the JVM through Gradle. For one-shot
CLIs that each run for a few seconds of *network* work, the JVM/Gradle
cold-start dominates wall-clock startup and makes iteration slow. The
PaddyPower migration already proved the pattern (a uv project, src
layout, pytest, injectable side effects). Finishing the job removes
the last JVM dependency and unifies the codebase.

"Faster" here means **startup/invocation latency**, not throughput —
the Betfair scraper is network-bound (Betfair Exchange API calls), so
Python does not make the actual scraping compute faster. It removes
the per-invocation JVM/Gradle boot.

## Non-goals

- **No JSON schema changes.** `betfair.json`, `paddypower.json`, and
  `arbs.json` keep their exact current shapes. The schema validators
  are the contract and are ported field-for-field. An external static
  site consumes `arbs.json` (and possibly the intermediates), so the
  output schemas are frozen; only on-disk formatting (indentation) is
  free to differ.
- **No behavior changes.** Same CLI args, same exit codes, same
  per-race drop rules, same stdout/stderr logging tone, same
  `run.sh [regions]` interface.
- **No new scraping sources or markets.** Pure port.
- **No retries.** The Kotlin clients have none; parity keeps none.
- **No concurrency.** Sequential, mirroring today.
- **PaddyPower scraping logic is not rewritten** — it is relocated and
  repointed at the shared `common` package. Its only *new* code is a
  Python schema validator (see below).

## Success criteria

1. `uv run pytest` is green, with the Kotlin test suite (~1936 lines)
   ported to pytest, test-per-module.
2. `betfair.json` and `arbs.json` produced by the Python programs
   pass the ported validators and round-trip stably against committed
   golden samples (no float/int/key-order drift vs. the old Gson
   output).
3. `./run.sh` and `./run.sh gb-ie,us` run the full pipeline end to end
   (Betfair → PaddyPower → arb) with the same exit-code semantics.
4. No Kotlin, Gradle, or JDK references remain in the repo (source,
   build files, README, run.sh, .gitignore).

## Project structure

One project at the repo root:

```
horsey-scraper/
├── pyproject.toml         # one project; deps: playwright (PP only) + pytest (dev)
├── uv.lock                # committed
├── README.md              # uv + Python 3.11 setup; pure-Python architecture
├── run.sh                 # 3 × `uv run python -m …`
├── src/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── regions.py        # REGION_COUNTRIES, parse_regions, countries_for_all
│   │   ├── timeutil.py       # utc_to_london, iso_utc, (build_off_time if needed)
│   │   ├── isovalid.py       # is_iso_utc, is_iso_offset_datetime
│   │   ├── markettype.py     # MarketType enum + top_n_from_places
│   │   └── jsonio.py         # dataclass→camelCase-dict serializer
│   ├── betfair_scraper/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── client.py
│   │   ├── responses.py
│   │   ├── credentials.py
│   │   ├── race_list.py
│   │   ├── race_odds.py
│   │   ├── assembly.py
│   │   ├── classifier.py
│   │   ├── pivot.py
│   │   ├── models.py
│   │   ├── validation.py
│   │   └── validate.py       # `python -m betfair_scraper.validate <file>`
│   ├── paddypower_scraper/   # moved from paddypower-py/, repointed to common
│   │   ├── … (existing modules)
│   │   ├── validation.py     # NEW — port of Kotlin PaddySchemaValidator
│   │   └── validate.py       # NEW — validate entry point
│   └── arb_finder/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── calculator.py
│       ├── models.py
│       ├── validation.py
│       └── validate.py
└── tests/                  # mirrors src/, includes fixtures/ and golden samples
```

`paddypower-py/` is deleted once its contents move.

### `pyproject.toml`

```toml
[project]
name = "horsey-scraper"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = ["playwright>=1.42"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
betfair-scraper    = "betfair_scraper.cli:main"
paddypower-scraper = "paddypower_scraper.cli:main"
arb-finder         = "arb_finder.cli:main"

[tool.hatch.build.targets.wheel]
packages = [
    "src/common",
    "src/betfair_scraper",
    "src/paddypower_scraper",
    "src/arb_finder",
]

[tool.pytest.ini_options]
markers = [
    "integration: live network/browser test, opt-in via RUN_INTEGRATION=1",
]
```

The `contract` marker is dropped — the cross-language gate disappears
when both validator and output are Python in one project.

## `common` package

Holds what is genuinely shared, eliminating duplication that today
spans the Kotlin tree and `paddypower-py`.

### `regions.py`

```python
REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us":    frozenset({"US"}),
}

def parse_regions(arg: str) -> frozenset[str]: ...
def countries_for_all(regions: frozenset[str]) -> frozenset[str]: ...
```

One `parse_regions` replaces both the Kotlin `parseRegions` and the
PaddyPower `parse_regions`. Their error-message wording differed
slightly; this picks one consistent form. The wording is stderr text,
**not** part of the JSON contract — the PaddyPower test that asserted
the old wording is updated.

### `markettype.py`

```python
class MarketType(enum.Enum):
    WIN = "WIN"; TOP_2 = "TOP_2"; TOP_3 = "TOP_3"
    TOP_4 = "TOP_4"; TOP_5 = "TOP_5"

def top_n_from_places(n: int) -> MarketType | None: ...
```

Used by `betfair_scraper` (output keys) and `arb_finder` (join +
classification). `MarketType` is serialized as its `.name`.

### `timeutil.py`

```python
def utc_to_london(iso_utc: str) -> str | None: ...   # ISO-8601 offset string
def iso_utc(dt: datetime) -> str: ...                # "...Z" UTC instant
```

`utc_to_london` consolidates Betfair's `utcToLondon` and PaddyPower's
`_utc_to_london` (verify identical during impl, then dedupe).

**Day-window functions stay package-local — they are NOT the same
function:**

- `betfair_scraper`: `london_day_window_utc(date) -> (from_utc, to_utc)`
  — the full London day from midnight, as ISO `Z` strings, used as the
  catalogue API time filter.
- `paddypower_scraper`: `london_day_window(now) -> (now, tomorrow_midnight)`
  — used to filter already-fetched races (already off races still pass).

Merging them would be a behavior bug; they live in their own packages.

### `isovalid.py`

```python
def is_iso_utc(v: str) -> bool: ...            # datetime.fromisoformat / Instant.parse equiv
def is_iso_offset_datetime(v: str) -> bool: ...
```

Shared by all three schema validators.

### `jsonio.py`

Generalizes PaddyPower's `output.py`. Walks a frozen-dataclass tree →
camelCase dict → `json.dump(indent=2)`:

- snake→camel field renaming via a **per-package mapping** passed in by
  the caller (each package owns its field-name map);
- `MarketType` keys/values → `.name`;
- `dict` keys that are `MarketType` → `.name`;
- `None` → `null`;
- list/nested-dataclass recursion;
- field order preserved from dataclass declaration order, matched to
  the current JSON files.

## `betfair_scraper` package

Module-by-module port of the Kotlin `com.horsey.scraper` package.

| Kotlin | Python module | Public surface |
|---|---|---|
| `Main.kt` | `cli.py` | `main(argv=None, *, make_client=…, now=…) -> int` |
| `BetfairClient.kt` | `client.py` | `BetfairClient(app_key).login(user, pw)`, `list_market_catalogue(body)`, `list_market_book(body)` |
| `BetfairResponses.kt` | `responses.py` | `parse_ssoid`, `race_from_catalogue`, `lay_prices_from_book`, `build_login_body`, `build_catalogue_body`, `build_book_body`, `MarketBookSnapshot`, `MarketBookStatus` |
| `Credentials.kt` | `credentials.py` | `Credentials`, `parse_credentials`, `default_credentials_path`, `load_credentials` |
| `RaceListFetcher.kt` | `race_list.py` | `parse_catalogue_races`, `london_day_window_utc`, `RaceListFetcher` |
| `RaceOddsFetcher.kt` | `race_odds.py` | `PlaceMarketEntry`, `chunk_of_40`, `parse_catalogue_place_markets`, `place_markets_by_race_id`, `parse_win_catalogue_runners`, `parse_book_snapshots`, `join_scrapes`, `parse_win_race_types`, `parse_win_race_keys`, `RaceOddsFetcher` |
| `RaceOddsAssembly.kt` | `assembly.py` | `format_market_name`, `assemble_race_odds` |
| `MarketClassifier.kt` | `classifier.py` | `classify_top_n` |
| `RunnerPivot.kt` | `pivot.py` | `pivot_market_scrapes` (phantom-horse stderr warnings preserved) |
| `Models.kt` | `models.py` | `Race`, `RunnerEntry`, `MarketScrape`, `RunnerOdds`, `RaceOdds`, `ScrapeOutput` + `ScrapeOutput.from_dict` |
| `SchemaValidator.kt` | `validation.py` | `validate_scrape_output(json_text) -> list[str]` |
| `ValidateMain.kt` | `validate.py` | `python -m betfair_scraper.validate <file>` (exit 0/1/2) |

### HTTP client

Betfair is a plain REST API with header auth (`X-Application`,
`X-Authentication`); no browser needed. `client.py` uses **stdlib
`urllib.request`** — zero new dependencies, fastest start. Timeouts
mirror Kotlin (login 15 s, betting 30 s, connect 10 s). Non-2xx →
raise with status + first 500 chars of body. Login failure → raise
(with the `LOGIN_RESTRICTED`/2FA hint). No retries.

### Credentials world-readable check

`load_credentials` warns to stderr if the file mode is wider than
`0600`, via `os.stat(path).st_mode & 0o077` (POSIX; a no-op concern on
non-POSIX). Same default path `~/.horsey-scraper/credentials.json`,
same JSON shape (`username`, `password`, `appKey`).

### Deserialization (new)

The arb finder must *read* `betfair.json`. Kotlin used Gson
reflection; Python adds `ScrapeOutput.from_dict(dict)` (camelCase →
snake, `MarketType` keys parsed from names, `selectionId` kept as
`int`). Validation runs on the raw text first; `from_dict` assumes a
validated payload.

### `cli.py` flow (parity with `Main.kt`)

1. `parse_regions(argv[0] or "gb-ie")`; bad arg → stderr, exit 1.
2. `load_credentials(default_credentials_path())`; failure → exit 2.
3. `BetfairClient(app_key).login(...)`; failure → exit 1.
4. `RaceListFetcher(client).fetch(regions)` → races (catalogue WIN);
   error → exit 1.
5. `RaceOddsFetcher(client).fetch(races, regions)` → list[RaceOdds];
   error → exit 1.
6. Log found/dropped races to stdout (same lines).
7. Write `betfair.json` with `scrapedAt = run_start`, `raceCount`,
   `races`.

`make_client` and `now` are injectable for tests (mirrors the Kotlin
`nowProvider` and the PaddyPower `make_session`).

## `arb_finder` package

| Kotlin | Python module | Surface |
|---|---|---|
| `ArbModels.kt` | `models.py` | `PaddyPriceLeg`, `BetfairLayLeg`, `ArbRunner`, `Arb`, `ArbOutput` |
| `ArbCalculator.kt` | `calculator.py` | `each_way_arb_margin(p, f, bw, bp)`, `find_arbs(betfair, paddy)` |
| `ArbSchemaValidator.kt` | `validation.py` | `validate_arbs_output(json_text) -> list[str]` |
| `ArbMain.kt` | `cli.py` | `parse_arb_cli_args`, `main(argv=None, *, now=…) -> int` |
| `ArbValidateMain.kt` | `validate.py` | validate entry point |

`calculator.find_arbs` consumes a `ScrapeOutput` (from
`betfair_scraper.models`) and a `PaddyOutput` (from
`paddypower_scraper.models`) — direct imports, the reason the project
is consolidated. `cli.py` reads both files, runs
`validate_scrape_output` / `validate_paddy_output` (exit 2 on either
failure), deserializes via the respective `from_dict`, computes, and
writes `arbs.json` (`computedAt`, `betfairScrapedAt`,
`paddypowerScrapedAt`, `arbCount`, `arbs`). CLI modes: 0 args
(defaults `betfair.json`, `paddypower.json`, `arbs.json`) or 3 args
(explicit paths); anything else → exit 1.

## PaddyPower fold-in

1. Move `paddypower-py/src/paddypower_scraper/` → `src/paddypower_scraper/`
   and `paddypower-py/tests/*` → `tests/` (+ `tests/fixtures/`).
   Delete `paddypower-py/`.
2. Repoint imports: `filtering.py` keeps PP-specific `in_window` and
   `london_day_window`, but imports `parse_regions` / `REGION_COUNTRIES`
   from `common.regions`. `races.py` uses `common.timeutil.utc_to_london`.
3. **Add `paddypower_scraper/validation.py`** — a Python port of the
   Kotlin `PaddySchemaValidator` (`validate_paddy_output`). This is new
   code: paddypower-py never had a Python validator; it depended on the
   Kotlin one through the opt-in contract test. Add a `validate.py`
   entry point too.
4. Add `PaddyOutput.from_dict` so the arb finder can read
   `paddypower.json` (PP only wrote before).
5. **Recolor the contract test**: `test_output.py`'s `RUN_CONTRACT`
   test that shelled out to the Kotlin validator becomes a plain
   in-process unit test (`validate_paddy_output(sample) == []`). Drop
   the `contract` marker and the `gradlew` subprocess.
6. Update stale "see Kotlin …" comments in `test_api.py` /
   `test_filtering.py` to point at `common` / the Python source.

## Kotlin / Gradle removal

**Delete:** `src/main/kotlin/`, `src/test/kotlin/`, `src/test/resources/`,
`build.gradle.kts`, `settings.gradle.kts`, `gradlew`, `gradlew.bat`,
`gradle/`, `.gradle/`, `build/`.

**`run.sh`:**

```bash
#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Pipeline: Betfair scrape → PaddyPower scrape → arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
REGIONS="${1:-gb-ie}"
uv run python -m betfair_scraper "$REGIONS"
uv run python -m paddypower_scraper "$REGIONS"
exec uv run python -m arb_finder
```

**`.gitignore`:** remove the Gradle/Kotlin sections (`.gradle/`,
`build/`, gradle-wrapper exception, `*.class`, `*.iml`/`*.iws`/`*.ipr`,
`out/`). Generalize the Python section to the repo root
(`.venv/`, `.pytest_cache/`, `**/__pycache__/`). Keep the output-file
and credentials ignores (`betfair.json`, `paddypower.json`,
`arbs.json`, `scraper.log`, `debug-page.html`, `credentials.json`,
`*.env`).

**`README.md`:** rewrite — prerequisites become uv + Python ≥3.11 +
`uv run playwright install chromium` (Betfair needs no browser, but the
project pulls Playwright for PP). Credentials section unchanged
(`~/.horsey-scraper/credentials.json`). Usage stays `./run.sh
[regions]`. Validation commands become
`uv run python -m betfair_scraper.validate betfair.json` (and the arb /
paddy equivalents). Architecture section rewritten to the Python
modules. All JDK/Gradle text removed.

## Testing strategy

Port the Kotlin test suite (~1936 lines) to pytest, test-per-module,
mirroring `src/`. **TDD**: for each module, port its tests first (they
encode the exact behavior), then port the implementation to green.
Injected fakes, no live network in unit tests.

| Kotlin test | Python test | Approach |
|---|---|---|
| `BetfairResponsesTest` | `test_responses.py` | parse ssoid (success/restricted/malformed), catalogue→Race, book→snapshot, body builders |
| `CredentialsTest` | `test_credentials.py` | parse happy/missing, file load, world-readable warning |
| `MarketClassifierTest`, `MarketTypeTest` | `test_classifier.py`, `test_markettype.py` | UI + API name forms, winners mismatch, top-N mapping |
| `ModelsJsonTest` | `test_models.py` / golden | serialize a `ScrapeOutput`, key order + camelCase + null lay + int selectionId |
| `ParseRegionsTest`, `RegionsTest` | `test_regions.py` | happy/unknown/empty; country union |
| `OffTimeBuilderTest`, `RaceIdParserTest` | only if the helpers survive (vestigial check) |
| `RaceListFetcherTest` | `test_race_list.py` | `FakeClient` returns canned catalogue JSON; dedupe + sort |
| `RaceOddsFetcherTest` | `test_race_odds.py` | `FakeClient` + canned catalogue/book JSON; place binding, chunking, join rules |
| `RaceOddsAssemblyTest` | `test_assembly.py` | market-name format, WIN-absent → None |
| `RunnerPivotTest` | `test_pivot.py` | key parity, phantom-horse warning, ordering |
| `SchemaValidatorTest` | `test_betfair_validation.py` | every validation branch |
| `SanityTest` | `test_sanity.py` | smoke |
| `ArbMainCliTest` | `test_arb_cli.py` | arg modes, file-missing/invalid → exit 2, write arbs.json |
| `ArbSchemaValidatorTest` | `test_arb_validation.py` | every branch |
| `EachWayArbMarginTest`, `FindArbsTest` | `test_calculator.py` | margin formula, skip rules, sort-desc |
| `PaddySchemaValidatorTest` | `test_paddy_validation.py` | port for the new Python validator |

Plus:
- **Golden round-trip tests** — commit one sanitized `betfair.json`
  and one `arbs.json` to `tests/fixtures/`; assert read→write (and for
  arb, read both inputs → compute → write) reproduces a stable shape.
  Guards float trailing `.0`, `int` selection ids, and key order
  against the old Gson output.
- **One opt-in `RUN_INTEGRATION=1`** Betfair-login smoke test (needs
  real creds; skipped by default), alongside PP's existing browser
  smoke test.

Commands: inner `uv run pytest tests/test_x.py -k name -x`; pre-commit
`uv run pytest`; pre-merge add `RUN_INTEGRATION=1 uv run pytest -m
integration`.

## Sequencing

De-risked order (the implementation plan expands each):

1. Scaffold the single project: `pyproject.toml`, `src/common/` with
   `regions`, `markettype`, `isovalid`, `timeutil`, `jsonio`, and their
   tests. `uv sync`.
2. Fold PaddyPower in: move src + tests, repoint to `common`, add
   `paddypower_scraper/validation.py` + `validate.py`, add
   `PaddyOutput.from_dict`, recolor the contract test. PP suite green.
3. Port `betfair_scraper` leaf-first (TDD): `responses`, `models`,
   `classifier`, `pivot`, `assembly`, `credentials` → `race_list`,
   `race_odds` → `validation` → `client` → `cli`.
4. Port `arb_finder` (TDD): `calculator`, `models`, `validation`,
   `cli`.
5. Wire entry points + `run.sh`, rewrite README, clean `.gitignore`.
6. Delete the Kotlin tree + Gradle files; regenerate & commit
   `uv.lock`.
7. Full `uv run pytest` green; optional end-to-end `./run.sh` smoke
   (needs creds + network).

## Risks and call-outs

- **`PaddySchemaValidator` port is new code**, not a move — easy to
  overlook because the other PaddyPower modules already exist in
  Python. The arb finder and the contract test both depend on it.
- **Serialization drift** vs. Gson: float trailing `.0`, `selectionId`
  must remain JSON `int` (not `66986352.0`), and key/field order must
  match. The golden round-trip tests are the guard.
- **`parse_regions` wording** changes for PaddyPower (one unified
  message). stderr only, not contract; update PP's test.
- **Two `london_day_window*` functions** have different semantics — do
  not merge.
- **`OffTimeBuilder` / `RaceIdParser`** appear vestigial (not on the
  API scrape path). Drop if unreferenced after porting; confirm during
  implementation.

## Appendix: current output shapes (frozen contract)

`betfair.json` (field order matters):

```
{ scrapedAt, raceCount, races: [
    { raceId, venue, country, offTime, winMarketUrl, marketName,
      marketScrapedAt: { WIN, TOP_2, … },
      runners: [ { name, lay: { WIN, TOP_2, … }, selectionId } ] } ] }
```

`arbs.json`:

```
{ computedAt, betfairScrapedAt, paddypowerScrapedAt, arbCount, arbs: [
    { venue, country, offTime, marketName, betfairWinMarketId,
      runner: { name, selectionId },
      paddypower: { winPrice, winPriceRaw, eachWayTerms: { fraction, places } },
      betfair: { winLay, topNLay, topNType }, margin } ] }
```

`paddypower.json` unchanged (already produced by the Python scraper).
