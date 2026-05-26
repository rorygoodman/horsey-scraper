# PaddyPower Python Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Kotlin `next-races` PaddyPower scraper with a standalone Python CLI that scrapes today's full PaddyPower racing card (every meeting, every race, every WIN market) and writes `paddypower.json` in the existing schema the Kotlin arb finder consumes.

**Architecture:** Standalone Python package in `paddypower-py/`, managed by `uv`. Playwright drives headless Chromium for Cloudflare-gated PaddyPower calls. Pipeline orchestration moves entirely into `run.sh`: Kotlin Betfair → Python PP → Kotlin arb finder, glued by `paddypower.json` file boundary. Spec: `docs/superpowers/specs/2026-05-26-paddypower-python-scraper-design.md`.

**Tech Stack:** Python 3.11+, uv, Playwright, pytest. Kotlin remnant unchanged (still owns Betfair scrape, arb finder, and the `paddypower.json` schema validator which now gates Python output).

---

## Task 1: Scaffold the `paddypower-py` uv project

**Files:**
- Create: `paddypower-py/pyproject.toml`
- Create: `paddypower-py/README.md`
- Create: `paddypower-py/src/paddypower_scraper/__init__.py`
- Create: `paddypower-py/src/paddypower_scraper/__main__.py`
- Modify: `.gitignore` (append Python/venv lines)

- [ ] **Step 1: Verify uv is installed**

Run: `command -v uv && uv --version`
Expected: prints a path and a version string.
If missing on macOS: `brew install uv`.
If missing on Linux/WSL: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 2: Create `paddypower-py/pyproject.toml`**

```toml
[project]
name = "paddypower-scraper"
version = "0.1.0"
description = "PaddyPower racing scraper (Python) for horsey-scraper pipeline"
requires-python = ">=3.11"
dependencies = ["playwright>=1.42"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
paddypower-scraper = "paddypower_scraper.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/paddypower_scraper"]

[tool.pytest.ini_options]
markers = [
    "integration: live network/browser test, opt-in via RUN_INTEGRATION=1",
    "contract: shells out to Kotlin schema validator, opt-in via RUN_CONTRACT=1",
]
```

- [ ] **Step 3: Create `paddypower-py/src/paddypower_scraper/__init__.py`**

```python
"""PaddyPower racing scraper. See cli.main for the entry point."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create `paddypower-py/src/paddypower_scraper/__main__.py`**

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 5: Create `paddypower-py/src/paddypower_scraper/cli.py` stub**

This is a placeholder so `python -m paddypower_scraper` doesn't crash before Task 10 lands the real implementation.

```python
def main(argv: list[str] | None = None) -> int:
    """Placeholder; real implementation arrives in Task 10."""
    print("paddypower_scraper: stub — implement in Task 10", flush=True)
    return 0
```

- [ ] **Step 6: Append to `.gitignore`**

Append these lines to the existing `.gitignore` at the repo root:

```
# Python / paddypower-py
paddypower-py/.venv/
paddypower-py/.pytest_cache/
paddypower-py/**/__pycache__/
paddypower-py/src/**/__pycache__/
paddypower-py/uv.lock.tmp
```

- [ ] **Step 7: Create `paddypower-py/README.md`**

```markdown
# paddypower-py

Python scraper for PaddyPower racing. Produces `paddypower.json` at the
repo root, consumed by the Kotlin arb finder.

## One-time setup

```bash
# Install uv (macOS) or via install script (Linux/WSL)
brew install uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync --project paddypower-py
uv run --project paddypower-py playwright install chromium
```

## Run manually

```bash
uv --project paddypower-py run python -m paddypower_scraper gb-ie
```

Valid regions: `gb-ie`, `us`, or any comma-separated combination
(e.g. `gb-ie,us`). Default: `gb-ie`.

## Test

```bash
uv --project paddypower-py run pytest                              # unit tests
RUN_INTEGRATION=1 uv --project paddypower-py run pytest -m integration   # real Chromium
RUN_CONTRACT=1 uv --project paddypower-py run pytest -m contract         # Kotlin schema validator
```

## Design

See `docs/superpowers/specs/2026-05-26-paddypower-python-scraper-design.md`.
```

- [ ] **Step 8: Install deps and Playwright Chromium**

Run:
```bash
uv sync --project paddypower-py
uv run --project paddypower-py playwright install chromium
```
Expected: `.venv/` created under `paddypower-py/`, deps resolved, Chromium download confirmation (or "already installed" if shared with the Kotlin Playwright cache).

- [ ] **Step 9: Smoke-test the stub**

Run: `uv --project paddypower-py run python -m paddypower_scraper`
Expected stdout: `paddypower_scraper: stub — implement in Task 10`
Expected exit code: 0.

- [ ] **Step 10: Commit**

```bash
git add paddypower-py/pyproject.toml paddypower-py/uv.lock paddypower-py/README.md paddypower-py/src .gitignore
git commit -m "$(cat <<'EOF'
Scaffold paddypower-py uv project

Empty package + __main__ stub so subsequent tasks can land module by
module via TDD without breaking the smoke run. uv-managed venv,
Playwright pinned, pytest markers registered for integration/contract
opt-in suites.
EOF
)"
```

---

## Task 2: Capture and sanitize test fixtures

**Files:**
- Create: `paddypower-py/tests/__init__.py`
- Create: `paddypower-py/tests/fixtures/card63_meetings.json` (sanitized from probe)
- Create: `paddypower-py/tests/fixtures/racing_page_meeting.json` (sanitized from probe)
- Create: `paddypower-py/tests/conftest.py` (fixture loader helpers)

The two raw probe dumps are at `/tmp/pp-race-content-managed-page_v7-4.json` and `/tmp/pp-race-racing-page_v7-1.json` from the brainstorming session. If those have been wiped, see "Re-capture probes" at the end of this task.

- [ ] **Step 1: Verify raw probe files exist**

Run: `ls -la /tmp/pp-race-content-managed-page_v7-4.json /tmp/pp-race-racing-page_v7-1.json`
Expected: both files listed, ~131KB and ~351KB respectively.
If missing, skip to "Re-capture probes" at the end of this task, then return here.

- [ ] **Step 2: Sanitize and save card63 fixture**

Run:
```bash
mkdir -p paddypower-py/tests/fixtures
uv --project paddypower-py run python - <<'PY'
import json
src = json.load(open('/tmp/pp-race-content-managed-page_v7-4.json'))
keep = {'races', 'meetings', 'eventTypes'}
src['attachments'] = {k: v for k, v in src.get('attachments', {}).items() if k in keep}
src.pop('layout', None)
with open('paddypower-py/tests/fixtures/card63_meetings.json', 'w') as f:
    json.dump(src, f, indent=2)
print('races:', len(src['attachments']['races']),
      'meetings:', len(src['attachments']['meetings']))
PY
```
Expected: prints `races: <some N around 400-500> meetings: <some M around 50-70>`.

- [ ] **Step 3: Sanitize and save racing-page fixture**

Run:
```bash
uv --project paddypower-py run python - <<'PY'
import json
src = json.load(open('/tmp/pp-race-racing-page_v7-1.json'))
keep = {'races', 'markets'}
out = {k: v for k, v in src.items() if k in keep}
with open('paddypower-py/tests/fixtures/racing_page_meeting.json', 'w') as f:
    json.dump(out, f, indent=2)
print('races:', len(out['races']), 'markets:', len(out['markets']))
PY
```
Expected: prints `races: 8 markets: 28` (Ballinrobe meeting from probe).

- [ ] **Step 4: Create `paddypower-py/tests/__init__.py`**

```python
```
(Empty file. Marks `tests` as a regular package so pytest's rootdir discovery works cleanly.)

- [ ] **Step 5: Create `paddypower-py/tests/conftest.py`**

```python
"""Shared pytest fixtures and helpers for paddypower-scraper tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


@pytest.fixture
def card63_payload() -> dict:
    """Raw meetings-index response (content-managed-page/v7?cardsToFetch=63)."""
    return _load("card63_meetings.json")


@pytest.fixture
def racing_page_payload() -> dict:
    """Raw per-meeting response (racing-page/v7?raceId=...) for Ballinrobe."""
    return _load("racing_page_meeting.json")


def mutate(payload: dict) -> dict:
    """Deep-copy a fixture so a test can mutate it without affecting others."""
    return copy.deepcopy(payload)
```

- [ ] **Step 6: Commit**

```bash
git add paddypower-py/tests/__init__.py paddypower-py/tests/conftest.py paddypower-py/tests/fixtures
git commit -m "$(cat <<'EOF'
Add sanitized PaddyPower probe fixtures for tests

card63_meetings.json: meetings-index response (446 races, 58 meetings),
trimmed to the attachment categories the parser actually reads.
racing_page_meeting.json: single-meeting per-race response (8 races,
28 markets at Ballinrobe), trimmed to top-level races+markets.
EOF
)"
```

**Re-capture probes (only if /tmp files are gone):**

If `/tmp/pp-race-*.json` is gone, create a temporary probe script and re-run it (Playwright must already be installed by Task 1):

```bash
uv --project paddypower-py run python - <<'PY'
from playwright.sync_api import sync_playwright
import json, pathlib

WARMUP = "https://www.paddypower.com/horse-racing"
INDEX = ("https://apisms.paddypower.com/smspp/content-managed-page/v7"
         "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl"
         "&cardsToFetch=63&countryCode=IE&currencyCode=EUR&eventTypeId=7"
         "&exchangeLocale=en_GB&includeEuromillionsWithoutLogin=false"
         "&includeMarketBlurbs=true&includePrices=true&includeRaceCards=true"
         "&language=en&layoutFetchedCardsOnly=true&loggedIn=false"
         "&nextRacesMarketsLimit=1&page=SPORT&priceHistory=3&regionCode=IRE"
         "&requestCountryCode=IE&staticCardsIncluded=SEO_CONTENT_SUMMARY"
         "&timezone=Europe%2FDublin")

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        locale="en-GB", timezone_id="Europe/Dublin")
    p = ctx.new_page()
    p.goto(WARMUP, timeout=25000); p.wait_for_load_state("domcontentloaded", timeout=15000)
    body = p.evaluate("async (u) => { const r = await fetch(u, {credentials:'include',headers:{accept:'application/json'}}); return await r.text(); }", INDEX)
    pathlib.Path("/tmp/pp-race-content-managed-page_v7-4.json").write_text(body)
    idx = json.loads(body)
    race_id = next(r["raceId"] for r in idx["attachments"]["races"].values()
                   if r.get("countryCode") in ("GB","IE") and r.get("winMarketId"))
    rp_url = f"https://apisms.paddypower.com/smspp/racing-page/v7?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl&currencyCode=EUR&eventTypeId=7&exchangeLocale=en_GB&includePrices=true&includeRaceTimeform=true&includeResults=true&language=en&priceHistory=3&raceId={race_id}&regionCode=IRE"
    body2 = p.evaluate("async (u) => { const r = await fetch(u, {credentials:'include',headers:{accept:'application/json'}}); return await r.text(); }", rp_url)
    pathlib.Path("/tmp/pp-race-racing-page_v7-1.json").write_text(body2)
    b.close()
print("re-captured both fixtures to /tmp")
PY
```

Then return to Step 2.

---

## Task 3: `models.py` — dataclasses

**Files:**
- Create: `paddypower-py/src/paddypower_scraper/models.py`

No tests here — dataclasses have no behaviour; they're covered transitively by `test_output.py` (Task 8). Just create the file so later modules can import from it.

- [ ] **Step 1: Create `paddypower-py/src/paddypower_scraper/models.py`**

```python
"""Dataclasses mirroring paddypower.json. snake_case here; the
snake→camel conversion happens in output.py."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    runners: list[PaddyRunner] = field(default_factory=list)


@dataclass(frozen=True)
class PaddyOutput:
    scraped_at: str
    race_count: int
    races: list[PaddyRace] = field(default_factory=list)


@dataclass(frozen=True)
class RaceStub:
    """Internal: metadata-only race entry from the meetings index.
    Not emitted in paddypower.json."""
    race_id: str
    meeting_id: str
    win_market_id: str
    start_time_utc: str
    country_code: str
    venue: str
```

- [ ] **Step 2: Smoke-import the module**

Run:
```bash
uv --project paddypower-py run python -c "from paddypower_scraper import models; print(models.EachWayTerms(0.2, 3))"
```
Expected: prints `EachWayTerms(fraction=0.2, places=3)`.

- [ ] **Step 3: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/models.py
git commit -m "Add models.py: dataclasses mirroring paddypower.json shape"
```

---

## Task 4: `filtering.py` — regions and London-day window (TDD)

**Files:**
- Create: `paddypower-py/tests/test_filtering.py`
- Create: `paddypower-py/src/paddypower_scraper/filtering.py`

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_filtering.py`:

```python
"""Tests for filtering.py: region parsing, London-day window, in-window check."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from paddypower_scraper.filtering import (
    REGION_COUNTRIES,
    in_window,
    london_day_window,
    parse_regions,
)


class TestParseRegions:
    def test_single_gb_ie(self):
        assert parse_regions("gb-ie") == frozenset({"GB", "IE"})

    def test_single_us(self):
        assert parse_regions("us") == frozenset({"US"})

    def test_combo(self):
        assert parse_regions("gb-ie,us") == frozenset({"GB", "IE", "US"})

    def test_whitespace_tolerant(self):
        assert parse_regions(" gb-ie ,  us ") == frozenset({"GB", "IE", "US"})

    def test_unknown_region_raises(self):
        with pytest.raises(ValueError, match="valid: gb-ie,us"):
            parse_regions("xx")

    def test_empty_arg_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("   ")


class TestLondonDayWindow:
    def test_bst_summer(self):
        # 2026-06-15 10:00 UTC = 11:00 BST. End-of-London-day = 23:00 UTC.
        now = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        start, end = london_day_window(now)
        assert start == now
        assert end == datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc)

    def test_gmt_winter(self):
        # 2026-12-15 10:00 UTC = 10:00 GMT. End-of-London-day = 24:00 UTC.
        now = datetime(2026, 12, 15, 10, 0, tzinfo=timezone.utc)
        start, end = london_day_window(now)
        assert start == now
        assert end == datetime(2026, 12, 16, 0, 0, tzinfo=timezone.utc)

    def test_just_before_midnight_bst(self):
        # 22:30 UTC in June = 23:30 BST. End is still today London = 23:00 UTC.
        now = datetime(2026, 6, 15, 22, 30, tzinfo=timezone.utc)
        _, end = london_day_window(now)
        # Window may be in the past, but the spec says "midnight of tomorrow London".
        # 23:30 BST → tomorrow London midnight = 2026-06-16 00:00 BST = 2026-06-15 23:00 UTC.
        assert end == datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc)


class TestInWindow:
    def test_race_inside_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert in_window("2026-06-15T15:00:00.000Z", win)

    def test_race_at_start_inclusive(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert in_window("2026-06-15T10:00:00.000Z", win)

    def test_race_at_end_exclusive(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-15T23:00:00.000Z", win)

    def test_race_before_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-15T09:59:59.000Z", win)

    def test_race_after_window(self):
        win = (
            datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        assert not in_window("2026-06-16T00:00:00.000Z", win)


class TestRegionCountries:
    def test_table_matches_kotlin(self):
        # Parity with Kotlin Regions.kt
        assert REGION_COUNTRIES == {
            "gb-ie": frozenset({"GB", "IE"}),
            "us": frozenset({"US"}),
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_filtering.py -v`
Expected: ImportError on `paddypower_scraper.filtering` (module doesn't exist yet).

- [ ] **Step 3: Implement `filtering.py`**

Create `paddypower-py/src/paddypower_scraper/filtering.py`:

```python
"""Region parsing and London-day windowing. Pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us": frozenset({"US"}),
}

_VALID_IDS_MSG = "valid: " + ",".join(sorted(REGION_COUNTRIES.keys()))


def parse_regions(arg: str) -> frozenset[str]:
    """Parse a comma-separated region string into a union of ISO country codes.

    Raises ValueError on empty input or any unknown region id."""
    stripped = arg.strip()
    if not stripped:
        raise ValueError(f"regions must be non-empty; {_VALID_IDS_MSG}")
    ids = [part.strip() for part in stripped.split(",")]
    unknown = [i for i in ids if i not in REGION_COUNTRIES]
    if unknown:
        raise ValueError(
            f"regions must be non-empty; {_VALID_IDS_MSG}, got: '{unknown[0]}'"
        )
    out: set[str] = set()
    for i in ids:
        out |= REGION_COUNTRIES[i]
    return frozenset(out)


def london_day_window(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return (now_utc, end_of_today_london_in_utc).

    `end` is midnight of *tomorrow* in Europe/London, converted back to UTC
    (exclusive upper bound). A race at 23:59 London passes; 00:00 next-day
    London does not."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    now_london = now_utc.astimezone(LONDON)
    tomorrow_london = (now_london + timedelta(days=1)).date()
    end_london = datetime.combine(tomorrow_london, time(0, 0), tzinfo=LONDON)
    end_utc = end_london.astimezone(timezone.utc)
    return (now_utc, end_utc)


def in_window(
    start_time_utc: str, window: tuple[datetime, datetime]
) -> bool:
    """`start_time_utc` is an ISO-8601 UTC string ('Z' or +00:00 form).
    Returns True iff window[0] <= parsed < window[1]."""
    # PaddyPower's startTime is '2026-05-26T17:39:00.000Z'. Python 3.11 fromisoformat
    # accepts 'Z' as a UTC suffix.
    parsed = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return window[0] <= parsed < window[1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv --project paddypower-py run pytest tests/test_filtering.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/filtering.py paddypower-py/tests/test_filtering.py
git commit -m "Add filtering.py: region parsing + London-day window"
```

---

## Task 5: `api.py` — URL constants and builder (TDD)

**Files:**
- Create: `paddypower-py/tests/test_api.py`
- Create: `paddypower-py/src/paddypower_scraper/api.py`

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_api.py`:

```python
"""Tests for api.py: URL constants and per-race URL builder."""

from urllib.parse import parse_qs, urlparse

from paddypower_scraper.api import (
    LOCALE,
    MEETINGS_INDEX_URL,
    TIMEZONE,
    USER_AGENT,
    WARMUP_URL,
    racing_page_url,
)


def _qs(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


class TestMeetingsIndexUrl:
    def test_targets_content_managed_page_v7(self):
        u = urlparse(MEETINGS_INDEX_URL)
        assert u.netloc == "apisms.paddypower.com"
        assert u.path == "/smspp/content-managed-page/v7"

    def test_cards_to_fetch_is_63(self):
        assert _qs(MEETINGS_INDEX_URL)["cardsToFetch"] == ["63"]

    def test_has_required_params(self):
        qs = _qs(MEETINGS_INDEX_URL)
        for key in (
            "_ak",
            "betexRegion",
            "countryCode",
            "eventTypeId",
            "includePrices",
            "language",
            "page",
            "regionCode",
            "timezone",
        ):
            assert key in qs, f"missing query param: {key}"

    def test_event_type_id_is_7(self):
        # 7 = horse racing in PaddyPower's taxonomy
        assert _qs(MEETINGS_INDEX_URL)["eventTypeId"] == ["7"]


class TestRacingPageUrl:
    def test_basic_shape(self):
        url = racing_page_url("35646567.1800")
        u = urlparse(url)
        assert u.netloc == "apisms.paddypower.com"
        assert u.path == "/smspp/racing-page/v7"
        assert _qs(url)["raceId"] == ["35646567.1800"]

    def test_includes_prices(self):
        assert _qs(racing_page_url("1.2"))["includePrices"] == ["true"]

    def test_race_id_with_dot_round_trips(self):
        # PaddyPower race ids contain a dot; ensure it survives URL encoding
        assert _qs(racing_page_url("35646567.1800"))["raceId"] == ["35646567.1800"]


class TestConstants:
    def test_warmup_url_is_horse_racing_landing(self):
        assert WARMUP_URL == "https://www.paddypower.com/horse-racing"

    def test_user_agent_is_chrome_like(self):
        assert "Chrome" in USER_AGENT
        assert "Mozilla" in USER_AGENT

    def test_locale_en_gb(self):
        assert LOCALE == "en-GB"

    def test_timezone_dublin(self):
        # Matches PaddyPower's regional API context — see Kotlin PaddyClient
        assert TIMEZONE == "Europe/Dublin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_api.py -v`
Expected: ImportError on `paddypower_scraper.api`.

- [ ] **Step 3: Implement `api.py`**

Create `paddypower-py/src/paddypower_scraper/api.py`:

```python
"""PaddyPower endpoint constants and URL builders. No I/O."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/Dublin"

WARMUP_URL = "https://www.paddypower.com/horse-racing"

# Captured 2026-05-26 from the meetings-results tab probe. Card id 63 is
# PaddyPower's "all today's meetings index" — see design spec appendix.
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

_RACING_PAGE_BASE = (
    "https://apisms.paddypower.com/smspp/racing-page/v7"
    "?_ak=vsd0Rm5ph2sS2uaK&betexRegion=IRL&capiJurisdiction=intl"
    "&currencyCode=EUR&eventTypeId=7&exchangeLocale=en_GB"
    "&includePrices=true&includeRaceTimeform=true&includeResults=true"
    "&language=en&priceHistory=3&regionCode=IRE"
)


def racing_page_url(race_id: str) -> str:
    """Build a racing-page/v7 URL for the meeting containing this raceId.

    One call returns every race in the meeting with WIN markets at top
    level (`races`, `markets`). raceId is any race in the meeting."""
    return f"{_RACING_PAGE_BASE}&raceId={quote(race_id, safe='.')}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv --project paddypower-py run pytest tests/test_api.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/api.py paddypower-py/tests/test_api.py
git commit -m "Add api.py: pinned PaddyPower endpoint URLs + per-race builder"
```

---

## Task 6: `meetings.py` — parse the card-63 meetings index (TDD)

**Files:**
- Create: `paddypower-py/tests/test_meetings.py`
- Create: `paddypower-py/src/paddypower_scraper/meetings.py`

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_meetings.py`:

```python
"""Tests for meetings.py: parsing the card-63 meetings index payload."""

from paddypower_scraper.meetings import parse_meetings_index
from paddypower_scraper.models import RaceStub

from .conftest import mutate


class TestParseMeetingsIndex:
    def test_returns_race_stubs(self, card63_payload):
        stubs = parse_meetings_index(card63_payload)
        assert len(stubs) > 100, "fixture should have hundreds of races"
        assert all(isinstance(s, RaceStub) for s in stubs)

    def test_stub_field_mapping(self, card63_payload):
        stubs = parse_meetings_index(card63_payload)
        first = stubs[0]
        # Every required field must be a non-empty string
        for field in ("race_id", "meeting_id", "win_market_id",
                      "start_time_utc", "country_code", "venue"):
            value = getattr(first, field)
            assert isinstance(value, str), f"{field} is {type(value).__name__}"
            assert value, f"{field} is empty"

    def test_drops_race_missing_country(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("countryCode", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_drops_race_missing_win_market_id(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("winMarketId", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_drops_race_missing_start_time(self, card63_payload):
        p = mutate(card63_payload)
        races = p["attachments"]["races"]
        victim_key = next(iter(races))
        races[victim_key].pop("startTime", None)
        stubs = parse_meetings_index(p)
        assert all(s.race_id != races[victim_key]["raceId"] for s in stubs)

    def test_empty_attachments(self):
        assert parse_meetings_index({}) == []
        assert parse_meetings_index({"attachments": {}}) == []
        assert parse_meetings_index({"attachments": {"races": {}}}) == []

    def test_returns_list_not_generator(self, card63_payload):
        result = parse_meetings_index(card63_payload)
        assert isinstance(result, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_meetings.py -v`
Expected: ImportError on `paddypower_scraper.meetings`.

- [ ] **Step 3: Implement `meetings.py`**

Create `paddypower-py/src/paddypower_scraper/meetings.py`:

```python
"""Parse the content-managed-page/v7?cardsToFetch=63 response.

This endpoint returns every race PaddyPower lists (spanning ~3 days,
all countries) with metadata only — no prices, no runners. Used as
the meetings index that drives per-meeting fan-out."""

from __future__ import annotations

from .models import RaceStub


def parse_meetings_index(payload: dict) -> list[RaceStub]:
    """Walk payload['attachments']['races'], emit one RaceStub per
    race that has all required metadata fields.

    Silently drops races missing any of: raceId, meetingId, winMarketId,
    startTime, countryCode, venue. Empty/missing attachments → []."""
    races = (
        payload.get("attachments", {})
        if isinstance(payload, dict) else {}
    ).get("races", {})
    if not isinstance(races, dict):
        return []
    out: list[RaceStub] = []
    for entry in races.values():
        if not isinstance(entry, dict):
            continue
        try:
            stub = RaceStub(
                race_id=entry["raceId"],
                meeting_id=entry["meetingId"],
                win_market_id=entry["winMarketId"],
                start_time_utc=entry["startTime"],
                country_code=entry["countryCode"],
                venue=entry["venue"],
            )
        except (KeyError, TypeError):
            continue
        # Defensive: drop entries with empty string values
        if not all((stub.race_id, stub.meeting_id, stub.win_market_id,
                    stub.start_time_utc, stub.country_code, stub.venue)):
            continue
        out.append(stub)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv --project paddypower-py run pytest tests/test_meetings.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/meetings.py paddypower-py/tests/test_meetings.py
git commit -m "Add meetings.py: parse card-63 meetings index → RaceStub list"
```

---

## Task 7: `races.py` — parse per-meeting WIN market data (TDD)

**Files:**
- Create: `paddypower-py/tests/test_races.py`
- Create: `paddypower-py/src/paddypower_scraper/races.py`

This is the biggest parser — multiple drop rules, helpers, edge cases.

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_races.py`:

```python
"""Tests for races.py: parsing the racing-page/v7 per-meeting response."""

import pytest

from paddypower_scraper.models import PaddyRace, PaddyRunner
from paddypower_scraper.races import (
    SYNTHETIC_RUNNER_NAMES,
    _market_name,
    _parse_eachway,
    _parse_runners,
    _utc_to_london,
    parse_meeting_response,
)

from .conftest import mutate

SCRAPED_AT = "2026-05-26T18:00:00Z"


class TestParseMeetingResponse:
    def test_returns_races(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        assert len(races) > 0
        assert all(isinstance(r, PaddyRace) for r in races)

    def test_skips_exchange_history_rows(self, racing_page_payload):
        # Some entries in payload['races'] have winMarketId=null (exchange results).
        # The fixture has these (raceIds starting with '1.201.').
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # Real bookmaker races have raceIds like '35646567.1800'
        for r in races:
            # Real races have venue / country / off_time populated
            assert r.venue
            assert r.country
            assert r.off_time

    def test_propagates_scraped_at(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        assert all(r.scraped_at == SCRAPED_AT for r in races)

    def test_each_way_terms_present(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # At least one race in the fixture has eachwayAvailable
        ew_races = [r for r in races if r.each_way_terms is not None]
        assert ew_races
        ew = ew_races[0].each_way_terms
        assert 0.0 < ew.fraction <= 1.0
        assert 1 <= ew.places <= 6

    def test_betfair_win_market_id_threaded(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # At least some races should have an exchange id
        with_id = [r for r in races if r.betfair_win_market_id]
        assert with_id

    def test_runners_populated_with_active_odds(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        any_runner_with_price = any(
            rr.win_price is not None for r in races for rr in r.runners
        )
        assert any_runner_with_price

    def test_drops_synthetic_runners(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        for r in races:
            for rr in r.runners:
                assert rr.name not in SYNTHETIC_RUNNER_NAMES

    def test_removed_runner_kept_with_null_prices(self, racing_page_payload):
        races = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        # The Ballinrobe fixture's first race has a REMOVED 'Grainne A Chroi'
        all_runners = [rr for r in races for rr in r.runners]
        non_runners = [rr for rr in all_runners
                       if rr.win_price is None and rr.win_price_raw is None]
        assert non_runners, "fixture should have at least one non-runner"

    def test_skips_race_with_missing_win_market(self, racing_page_payload):
        baseline = parse_meeting_response(racing_page_payload, SCRAPED_AT)
        p = mutate(racing_page_payload)
        # Pick the first race with a winMarketId; delete that market.
        victim_wmid = next(
            r["winMarketId"] for r in p["races"].values() if r.get("winMarketId")
        )
        del p["markets"][victim_wmid]
        races = parse_meeting_response(p, SCRAPED_AT)
        assert len(races) == len(baseline) - 1

    def test_market_with_eachway_unavailable(self, racing_page_payload):
        p = mutate(racing_page_payload)
        for m in p["markets"].values():
            m["eachwayAvailable"] = False
        races = parse_meeting_response(p, SCRAPED_AT)
        assert all(r.each_way_terms is None for r in races)


class TestParseRunners:
    def _market(self, runners):
        return {"runners": runners}

    def test_synthetic_dropped(self):
        m = self._market([
            {"runnerName": "Unnamed Favourite", "selectionId": 1,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 2.0},
                 "fractionalOdds": {"numerator": 1, "denominator": 1}}}},
            {"runnerName": "Real Horse", "selectionId": 2,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 3.0},
                 "fractionalOdds": {"numerator": 2, "denominator": 1}}}},
        ])
        runners = _parse_runners(m)
        assert [r.name for r in runners] == ["Real Horse"]

    def test_removed_keeps_runner_null_prices(self):
        m = self._market([
            {"runnerName": "Withdrawn", "selectionId": 7,
             "runnerStatus": "REMOVED",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 5.0},
                 "fractionalOdds": {"numerator": 4, "denominator": 1}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Withdrawn", selection_id=7,
                                       win_price=None, win_price_raw=None)]

    def test_active_with_valid_odds(self):
        m = self._market([
            {"runnerName": "Live Horse", "selectionId": 9,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 7.5},
                 "fractionalOdds": {"numerator": 13, "denominator": 2}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Live Horse", selection_id=9,
                                       win_price=7.5, win_price_raw="13/2")]

    def test_parity_invariant_malformed_fractional_nulls_both(self):
        m = self._market([
            {"runnerName": "Half Odds", "selectionId": 3,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {"trueOdds": {
                 "decimalOdds": {"decimalOdds": 4.0},
                 # numerator/denominator missing — malformed fractional
                 "fractionalOdds": {}}}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="Half Odds", selection_id=3,
                                       win_price=None, win_price_raw=None)]

    def test_active_without_odds_nulls_both(self):
        m = self._market([
            {"runnerName": "No Odds", "selectionId": 4,
             "runnerStatus": "ACTIVE",
             "winRunnerOdds": {}},
        ])
        runners = _parse_runners(m)
        assert runners == [PaddyRunner(name="No Odds", selection_id=4,
                                       win_price=None, win_price_raw=None)]

    def test_missing_runner_name_skipped(self):
        m = self._market([
            {"selectionId": 11, "runnerStatus": "ACTIVE"},
            {"runnerName": "Named", "selectionId": 12, "runnerStatus": "ACTIVE",
             "winRunnerOdds": {}},
        ])
        runners = _parse_runners(m)
        assert [r.name for r in runners] == ["Named"]


class TestParseEachway:
    def test_unavailable(self):
        assert _parse_eachway({"eachwayAvailable": False}) is None

    def test_missing_places(self):
        assert _parse_eachway({"eachwayAvailable": True}) is None

    def test_zero_places(self):
        assert _parse_eachway({"eachwayAvailable": True, "numberOfPlaces": 0,
                               "placeFraction": {"numerator": 1, "denominator": 5}}) is None

    def test_missing_fraction(self):
        assert _parse_eachway({"eachwayAvailable": True, "numberOfPlaces": 3}) is None

    def test_invalid_fraction(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 2, "denominator": 1}}  # 2/1 > 1
        assert _parse_eachway(m) is None

    def test_zero_denominator(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 0}}
        assert _parse_eachway(m) is None

    def test_valid_fifth(self):
        m = {"eachwayAvailable": True, "numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 5}}
        ew = _parse_eachway(m)
        assert ew is not None
        assert ew.fraction == pytest.approx(0.2)
        assert ew.places == 3

    def test_default_true_when_field_missing(self):
        # Spec: when eachwayAvailable is absent, treat as True (parity with Kotlin)
        m = {"numberOfPlaces": 3,
             "placeFraction": {"numerator": 1, "denominator": 4}}
        ew = _parse_eachway(m)
        assert ew is not None
        assert ew.places == 3


class TestUtcToLondon:
    def test_bst(self):
        assert _utc_to_london("2026-06-15T17:00:00.000Z") == "2026-06-15T18:00:00+01:00"

    def test_gmt(self):
        assert _utc_to_london("2026-12-15T17:00:00.000Z") == "2026-12-15T17:00:00Z"

    def test_invalid_returns_none(self):
        assert _utc_to_london("not-a-date") is None

    def test_empty_returns_none(self):
        assert _utc_to_london("") is None


class TestMarketName:
    def test_with_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "2m1f Hcap Chs") == \
            "18:00 Plumpton - 2m1f Hcap Chs"

    def test_without_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "") == \
            "18:00 Plumpton"

    def test_blank_race_type(self):
        assert _market_name("2026-06-15T18:00:00+01:00", "Plumpton", "   ") == \
            "18:00 Plumpton"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_races.py -v`
Expected: ImportError on `paddypower_scraper.races`.

- [ ] **Step 3: Implement `races.py`**

Create `paddypower-py/src/paddypower_scraper/races.py`:

```python
"""Parse the racing-page/v7 response into PaddyRace objects.

This endpoint returns the whole meeting (every race) plus every market
for those races at TOP LEVEL (not under 'attachments' like the
content-managed-page response — that's the gotcha that justifies a
separate parser module)."""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import EachWayTerms, PaddyRace, PaddyRunner

LONDON = ZoneInfo("Europe/London")

SYNTHETIC_RUNNER_NAMES = frozenset({
    "Unnamed Favourite",
    "Unnamed 2nd Favourite",
    "The Field",
})


def parse_meeting_response(
    payload: dict, scraped_at_utc: str
) -> list[PaddyRace]:
    """Iterate payload['races'] and build PaddyRace records.

    Skips entries where winMarketId is null (exchange-history rows) or
    the WIN market is missing from payload['markets']. Drops races with
    no usable runners. Logs (stderr) when dropping a race for missing
    country code."""
    races = payload.get("races", {})
    markets = payload.get("markets", {})
    if not isinstance(races, dict) or not isinstance(markets, dict):
        return []

    out: list[PaddyRace] = []
    for race in races.values():
        if not isinstance(race, dict):
            continue
        win_market_id = race.get("winMarketId")
        if not win_market_id:
            continue  # exchange-history row
        market = markets.get(win_market_id)
        if not isinstance(market, dict):
            continue  # market missing — skip silently
        venue = race.get("venue") or ""
        country = race.get("countryCode")
        if not country:
            print(
                f"paddy: dropping race {race.get('raceId')} venue={venue}: "
                "no countryCode",
                file=sys.stderr,
            )
            continue
        start_time_utc = race.get("startTime")
        if not start_time_utc:
            continue
        off_time = _utc_to_london(start_time_utc)
        if off_time is None:
            continue
        runners = _parse_runners(market)
        if not runners:
            continue
        ew = _parse_eachway(market)
        race_type = race.get("winMarketName") or market.get("marketName") or ""
        out.append(PaddyRace(
            venue=venue,
            country=country,
            off_time=off_time,
            market_name=_market_name(off_time, venue, race_type),
            race_url="",  # racing-page response doesn't expose a stable per-race URL
            scraped_at=scraped_at_utc,
            betfair_win_market_id=market.get("exchangeMarketId"),
            each_way_terms=ew,
            runners=runners,
        ))
    return out


def _parse_runners(market: dict) -> list[PaddyRunner]:
    raw = market.get("runners", [])
    if not isinstance(raw, list):
        return []
    out: list[PaddyRunner] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        name = r.get("runnerName")
        if not isinstance(name, str) or not name:
            continue
        if name in SYNTHETIC_RUNNER_NAMES:
            continue
        selection_id = r.get("selectionId")
        if not isinstance(selection_id, int):
            selection_id = None
        status = r.get("runnerStatus") or "ACTIVE"
        odds = r.get("winRunnerOdds")
        odds = odds.get("trueOdds") if isinstance(odds, dict) else None
        is_active_with_odds = status == "ACTIVE" and isinstance(odds, dict) and odds
        decimal_val = None
        fractional_val = None
        if is_active_with_odds:
            d = odds.get("decimalOdds")
            if isinstance(d, dict):
                v = d.get("decimalOdds")
                if isinstance(v, (int, float)):
                    decimal_val = float(v)
            f = odds.get("fractionalOdds")
            if isinstance(f, dict):
                num = f.get("numerator")
                den = f.get("denominator")
                if isinstance(num, int) and isinstance(den, int):
                    fractional_val = f"{num}/{den}"
        # Parity invariant: both populated or both null
        if decimal_val is None or fractional_val is None:
            decimal_val = None
            fractional_val = None
        out.append(PaddyRunner(
            name=name,
            selection_id=selection_id,
            win_price=decimal_val,
            win_price_raw=fractional_val,
        ))
    return out


def _parse_eachway(market: dict) -> EachWayTerms | None:
    # Default True when field absent — parity with Kotlin parser
    available = market.get("eachwayAvailable", True)
    if available is False:
        return None
    places = market.get("numberOfPlaces")
    if not isinstance(places, int) or places <= 0:
        return None
    frac = market.get("placeFraction")
    if not isinstance(frac, dict):
        return None
    num = frac.get("numerator")
    den = frac.get("denominator")
    if not isinstance(num, int) or not isinstance(den, int) or den == 0:
        return None
    fraction = num / den
    if fraction <= 0.0 or fraction > 1.0:
        return None
    return EachWayTerms(fraction=fraction, places=places)


def _utc_to_london(iso_utc: str) -> str | None:
    """'2026-05-26T17:39:00.000Z' → '2026-05-26T18:39:00+01:00' (BST)
    or '...Z' (GMT). Returns None on parse failure."""
    if not iso_utc:
        return None
    try:
        parsed = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    london = parsed.astimezone(LONDON)
    # Format identical to Java's ISO_OFFSET_DATE_TIME: '+01:00' or 'Z'
    s = london.isoformat(timespec="seconds")
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    return s


def _market_name(off_time_london: str, venue: str, race_type: str) -> str:
    # off_time_london is '2026-06-15T18:00:00+01:00'; pull out 'HH:mm'
    try:
        time_part = off_time_london[11:16]
    except IndexError:
        time_part = ""
    if race_type and race_type.strip():
        return f"{time_part} {venue} - {race_type.strip()}"
    return f"{time_part} {venue}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv --project paddypower-py run pytest tests/test_races.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/races.py paddypower-py/tests/test_races.py
git commit -m "Add races.py: parse racing-page/v7 → PaddyRace with drop rules"
```

---

## Task 8: `output.py` — atomic JSON write with camelCase mapping (TDD)

**Files:**
- Create: `paddypower-py/tests/test_output.py`
- Create: `paddypower-py/src/paddypower_scraper/output.py`

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_output.py`:

```python
"""Tests for output.py: write paddypower.json with camelCase keys."""

import json
from pathlib import Path

from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)
from paddypower_scraper.output import write_paddypower_json


def _sample_output() -> PaddyOutput:
    return PaddyOutput(
        scraped_at="2026-05-26T18:00:00Z",
        race_count=1,
        races=[PaddyRace(
            venue="Plumpton",
            country="GB",
            off_time="2026-05-26T18:39:00+01:00",
            market_name="18:39 Plumpton - 3m1f Hcap Hrd",
            race_url="",
            scraped_at="2026-05-26T18:00:00Z",
            betfair_win_market_id="1.258556270",
            each_way_terms=EachWayTerms(fraction=0.2, places=3),
            runners=[
                PaddyRunner(name="Live Horse", selection_id=9,
                            win_price=7.5, win_price_raw="13/2"),
                PaddyRunner(name="Withdrawn", selection_id=7,
                            win_price=None, win_price_raw=None),
            ],
        )],
    )


class TestWritePaddypowerJson:
    def test_writes_file_with_camel_case(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        assert data["scrapedAt"] == "2026-05-26T18:00:00Z"
        assert data["raceCount"] == 1
        race = data["races"][0]
        assert race["venue"] == "Plumpton"
        assert race["country"] == "GB"
        assert race["offTime"] == "2026-05-26T18:39:00+01:00"
        assert race["marketName"] == "18:39 Plumpton - 3m1f Hcap Hrd"
        assert race["raceUrl"] == ""
        assert race["scrapedAt"] == "2026-05-26T18:00:00Z"
        assert race["betfairWinMarketId"] == "1.258556270"
        assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
        runner = race["runners"][0]
        assert runner["name"] == "Live Horse"
        assert runner["selectionId"] == 9
        assert runner["winPrice"] == 7.5
        assert runner["winPriceRaw"] == "13/2"

    def test_none_becomes_null(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        withdrawn = data["races"][0]["runners"][1]
        assert withdrawn["winPrice"] is None
        assert withdrawn["winPriceRaw"] is None

    def test_each_way_terms_can_be_null(self, tmp_path: Path):
        o = PaddyOutput(scraped_at="2026-05-26T18:00:00Z", race_count=1, races=[
            PaddyRace(venue="X", country="GB", off_time="2026-05-26T18:00:00+01:00",
                      market_name="18:00 X", race_url="", scraped_at="2026-05-26T18:00:00Z",
                      betfair_win_market_id=None, each_way_terms=None, runners=[
                          PaddyRunner(name="A", selection_id=1, win_price=None, win_price_raw=None)
                      ])])
        out = tmp_path / "paddypower.json"
        write_paddypower_json(o, out)
        data = json.loads(out.read_text())
        assert data["races"][0]["eachWayTerms"] is None
        assert data["races"][0]["betfairWinMarketId"] is None

    def test_no_tmp_file_left_behind(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        assert out.exists()
        assert not (tmp_path / "paddypower.json.tmp").exists()

    def test_empty_races(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(
            PaddyOutput(scraped_at="2026-05-26T18:00:00Z", race_count=0, races=[]),
            out,
        )
        data = json.loads(out.read_text())
        assert data == {"scrapedAt": "2026-05-26T18:00:00Z", "raceCount": 0, "races": []}

    def test_overwrites_existing(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        out.write_text('{"old": true}')
        write_paddypower_json(_sample_output(), out)
        data = json.loads(out.read_text())
        assert "old" not in data
        assert data["raceCount"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_output.py -v`
Expected: ImportError on `paddypower_scraper.output`.

- [ ] **Step 3: Implement `output.py`**

Create `paddypower-py/src/paddypower_scraper/output.py`:

```python
"""Serialize PaddyOutput to JSON with camelCase keys, atomic write."""

from __future__ import annotations

import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path

from .models import PaddyOutput

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


def _to_dict(obj):
    if is_dataclass(obj):
        out = {}
        for f in fields(obj):
            key = _SNAKE_TO_CAMEL.get(f.name, f.name)
            out[key] = _to_dict(getattr(obj, f.name))
        return out
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    return obj


def write_paddypower_json(out: PaddyOutput, path: Path) -> None:
    """Serialize `out` to `path` as JSON with camelCase keys.

    Atomic: writes to `{path}.tmp` then `os.replace`s into place. Same
    directory as `path`, so the rename is on one filesystem."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = _to_dict(out)
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv --project paddypower-py run pytest tests/test_output.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/output.py paddypower-py/tests/test_output.py
git commit -m "Add output.py: atomic paddypower.json write with camelCase mapping"
```

---

## Task 9: `browser.py` — Playwright session + opt-in smoke test

**Files:**
- Create: `paddypower-py/src/paddypower_scraper/browser.py`
- Create: `paddypower-py/tests/test_browser_smoke.py`

`BrowserSession` is a thin wrapper around Playwright. The only meaningful test is an opt-in live-network smoke that hits `MEETINGS_INDEX_URL` end to end and verifies the response shape.

- [ ] **Step 1: Implement `browser.py`**

Create `paddypower-py/src/paddypower_scraper/browser.py`:

```python
"""Playwright-driven browser session for Cloudflare-gated PaddyPower calls.

One BrowserSession per scraper run. Warms up once on __enter__ to earn
the cf_clearance cookie, then reuses the same browser context for every
fetch_json call."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Type

from playwright.sync_api import Playwright, sync_playwright

from .api import LOCALE, TIMEZONE, USER_AGENT, WARMUP_URL


class BrowserFetchError(Exception):
    """Raised when an in-page fetch returns non-2xx, fails to evaluate,
    or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


_FETCH_JS = """
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
"""


class BrowserSession:
    """Context manager. Launches headless Chromium and warms it up on
    __enter__; closes everything on __exit__."""

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
        )
        self._page = self._context.new_page()
        self._page.goto(WARMUP_URL, timeout=20_000)
        self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        """Run an in-page fetch() against `url` and return the parsed JSON.

        Raises BrowserFetchError on HTTP non-2xx, evaluation failure, or
        invalid JSON."""
        if self._page is None:
            raise RuntimeError("BrowserSession not entered")
        try:
            body = self._page.evaluate(_FETCH_JS, url)
        except Exception as e:
            raise BrowserFetchError(url, str(e)) from e
        if not isinstance(body, str):
            raise BrowserFetchError(url, f"unexpected response type: {type(body).__name__}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise BrowserFetchError(url, f"invalid JSON: {e}") from e
```

- [ ] **Step 2: Create the opt-in smoke test**

Create `paddypower-py/tests/test_browser_smoke.py`:

```python
"""Opt-in integration test: launches real Chromium and hits PaddyPower.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration"""

import os

import pytest

from paddypower_scraper.api import MEETINGS_INDEX_URL
from paddypower_scraper.browser import BrowserSession

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 to run live-network browser tests",
)
class TestBrowserSessionLive:
    def test_fetch_meetings_index_returns_dict_with_attachments(self):
        with BrowserSession() as s:
            data = s.fetch_json(MEETINGS_INDEX_URL)
        assert isinstance(data, dict)
        assert "attachments" in data
        races = data["attachments"].get("races", {})
        assert isinstance(races, dict)
        assert len(races) > 0, "expected at least one race in the meetings index"
```

- [ ] **Step 3: Run the smoke test once manually**

Run:
```bash
RUN_INTEGRATION=1 uv --project paddypower-py run pytest tests/test_browser_smoke.py -v
```
Expected: 1 passed (takes ~10-15s for browser launch + warmup + fetch).
If Cloudflare blocks: verify `playwright install chromium` ran in Task 1.

- [ ] **Step 4: Verify default `pytest` run skips the smoke**

Run: `uv --project paddypower-py run pytest tests/test_browser_smoke.py -v`
Expected: 1 skipped (no browser launch).

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/browser.py paddypower-py/tests/test_browser_smoke.py
git commit -m "Add browser.py: Playwright session with in-page fetch + opt-in smoke"
```

---

## Task 10: `cli.py` — orchestration with injectable session (TDD)

**Files:**
- Modify: `paddypower-py/src/paddypower_scraper/cli.py` (replace stub)
- Create: `paddypower-py/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `paddypower-py/tests/test_cli.py`:

```python
"""Tests for cli.py: orchestration with a FakeSession injected.

No real browser. Covers happy path, partial failure, all-fail,
index-fail, bad args, empty day, region filtering, today window."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from paddypower_scraper import api, cli
from paddypower_scraper.browser import BrowserFetchError


# --- Test doubles ---

class FakeSession:
    """Returns canned dicts from a URL → payload map. Raises if a URL
    not in the map is requested. Use `errors` to register URLs that
    should raise BrowserFetchError instead."""

    def __init__(self, responses: dict[str, dict], errors: dict[str, str] | None = None):
        self.responses = responses
        self.errors = errors or {}
        self.calls: list[str] = []

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.calls.append(url)
        if url in self.errors:
            raise BrowserFetchError(url, self.errors[url])
        if url not in self.responses:
            raise AssertionError(f"unexpected URL in test: {url}")
        return self.responses[url]


def make_session_factory(session: FakeSession):
    @contextmanager
    def _factory():
        yield session
    return _factory


# --- Fixture data ---

def _index_payload(races: list[dict]) -> dict:
    return {"attachments": {"races": {r["raceId"]: r for r in races}}}


def _race_meta(*, race_id, meeting_id, win_market_id, start_time, country, venue):
    return {
        "raceId": race_id,
        "meetingId": meeting_id,
        "winMarketId": win_market_id,
        "startTime": start_time,
        "countryCode": country,
        "venue": venue,
    }


def _meeting_payload(race_id: str, win_market_id: str,
                     start_time: str, venue: str, country: str) -> dict:
    return {
        "races": {
            race_id: {
                "raceId": race_id,
                "winMarketId": win_market_id,
                "startTime": start_time,
                "venue": venue,
                "countryCode": country,
                "winMarketName": "Test Race",
            }
        },
        "markets": {
            win_market_id: {
                "marketName": "Test Race",
                "exchangeMarketId": f"1.exchange_{race_id}",
                "eachwayAvailable": True,
                "numberOfPlaces": 3,
                "placeFraction": {"numerator": 1, "denominator": 5},
                "runners": [
                    {"runnerName": "Horse A", "selectionId": 1, "runnerStatus": "ACTIVE",
                     "winRunnerOdds": {"trueOdds": {
                         "decimalOdds": {"decimalOdds": 4.0},
                         "fractionalOdds": {"numerator": 3, "denominator": 1},
                     }}},
                ],
            }
        },
    }


# --- Tests ---

NOW = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)


class TestHappyPath:
    def test_writes_paddypower_json(self, tmp_path: Path):
        index_race = _race_meta(
            race_id="100.1800", meeting_id="100", win_market_id="927.1",
            start_time="2026-05-26T18:00:00.000Z", country="GB", venue="Plumpton",
        )
        meeting = _meeting_payload("100.1800", "927.1",
                                   "2026-05-26T18:00:00.000Z", "Plumpton", "GB")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([index_race]),
            api.racing_page_url("100.1800"): meeting,
        }
        session = FakeSession(responses)
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["raceCount"] == 1
        assert data["races"][0]["venue"] == "Plumpton"


class TestPartialFailure:
    def test_one_meeting_fails_rest_succeeds(self, tmp_path: Path):
        good = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        bad = _race_meta(race_id="200.1900", meeting_id="200", win_market_id="927.2",
                         start_time="2026-05-26T19:00:00.000Z", country="GB",
                         venue="Lingfield")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([good, bad]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        errors = {api.racing_page_url("200.1900"): "HTTP 500"}
        session = FakeSession(responses, errors)
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0  # partial success → 0
        data = json.loads(out.read_text())
        assert data["raceCount"] == 1
        assert data["races"][0]["venue"] == "Plumpton"


class TestAllMeetingsFail:
    def test_exits_one(self, tmp_path: Path):
        race = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                          start_time="2026-05-26T18:00:00.000Z", country="GB",
                          venue="Plumpton")
        responses = {api.MEETINGS_INDEX_URL: _index_payload([race])}
        errors = {api.racing_page_url("100.1800"): "HTTP 503"}
        session = FakeSession(responses, errors)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1


class TestIndexFetchFails:
    def test_exits_one(self, tmp_path: Path):
        session = FakeSession({}, {api.MEETINGS_INDEX_URL: "HTTP 503"})
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 1


class TestBadArgs:
    def test_unknown_region_exits_two(self, tmp_path: Path):
        session = FakeSession({})
        rc = cli.main(
            ["xx"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 2

    def test_default_region_is_gb_ie(self, tmp_path: Path):
        # No args → default 'gb-ie'. Index returns nothing → empty day path.
        session = FakeSession({api.MEETINGS_INDEX_URL: _index_payload([])})
        rc = cli.main(
            [],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0


class TestLegitimateEmptyDay:
    def test_writes_empty_output_exits_zero(self, tmp_path: Path):
        session = FakeSession({api.MEETINGS_INDEX_URL: _index_payload([])})
        out = tmp_path / "paddypower.json"
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=out,
        )
        assert rc == 0
        data = json.loads(out.read_text())
        assert data == {"scrapedAt": data["scrapedAt"], "raceCount": 0, "races": []}


class TestRegionFiltering:
    def test_us_race_excluded_from_gb_ie_run(self, tmp_path: Path):
        gb = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                        start_time="2026-05-26T18:00:00.000Z", country="GB",
                        venue="Plumpton")
        us = _race_meta(race_id="200.2200", meeting_id="200", win_market_id="927.2",
                        start_time="2026-05-26T22:00:00.000Z", country="US",
                        venue="Finger Lakes")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([gb, us]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0
        # Only Plumpton was fanned out; Finger Lakes filtered before fetch
        fanout_calls = [u for u in session.calls if "racing-page" in u]
        assert len(fanout_calls) == 1


class TestTodayWindowFiltering:
    def test_tomorrow_race_excluded(self, tmp_path: Path):
        today = _race_meta(race_id="100.1800", meeting_id="100", win_market_id="927.1",
                           start_time="2026-05-26T18:00:00.000Z", country="GB",
                           venue="Plumpton")
        tomorrow = _race_meta(race_id="200.1800", meeting_id="200", win_market_id="927.2",
                              start_time="2026-05-27T18:00:00.000Z", country="GB",
                              venue="Lingfield")
        responses = {
            api.MEETINGS_INDEX_URL: _index_payload([today, tomorrow]),
            api.racing_page_url("100.1800"): _meeting_payload(
                "100.1800", "927.1", "2026-05-26T18:00:00.000Z", "Plumpton", "GB"),
        }
        session = FakeSession(responses)
        rc = cli.main(
            ["gb-ie"],
            now_utc=NOW,
            make_session=make_session_factory(session),
            out_path=tmp_path / "paddypower.json",
        )
        assert rc == 0
        fanout_calls = [u for u in session.calls if "racing-page" in u]
        assert len(fanout_calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv --project paddypower-py run pytest tests/test_cli.py -v`
Expected: failures because `cli.main` is the stub from Task 1 and doesn't accept keyword args / doesn't write the file.

- [ ] **Step 3: Replace `cli.py` with the real implementation**

Overwrite `paddypower-py/src/paddypower_scraper/cli.py`:

```python
"""Top-level orchestration. Pure functions everywhere except the
BrowserSession side effect, which is injectable for tests."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

from . import api
from .browser import BrowserFetchError, BrowserSession
from .filtering import in_window, london_day_window, parse_regions
from .meetings import parse_meetings_index
from .models import PaddyOutput, PaddyRace, RaceStub
from .output import write_paddypower_json
from .races import parse_meeting_response


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("paddypower.json"),
) -> int:
    """Return process exit code (0 = success or partial, 1 = fetch error,
    2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        countries = parse_regions(region_arg)
    except ValueError as e:
        print(f"paddypower-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching PaddyPower meetings for regions={region_arg}...")

    with make_session() as session:
        # Index fetch — catastrophic if it fails.
        try:
            index_payload = session.fetch_json(api.MEETINGS_INDEX_URL)
        except BrowserFetchError as e:
            print(f"paddy: meetings index fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_meetings_index(index_payload)
        in_region = [s for s in stubs if s.country_code in countries]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        meetings = _group_by_meeting(in_today)
        if not meetings:
            # Legitimate empty day: write empty output and exit 0.
            _write(out_path, now, [])
            print(
                f"Wrote {out_path} (0 races from 0 meetings, 0 skipped)"
            )
            return 0

        all_races: list[PaddyRace] = []
        skipped = 0
        attempted = 0
        for meeting_id, stubs_in_meeting in meetings.items():
            attempted += 1
            anchor = stubs_in_meeting[0]
            url = api.racing_page_url(anchor.race_id)
            scraped_at = _iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                meeting_races = parse_meeting_response(payload, scraped_at)
            except BrowserFetchError as e:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: {e.reason}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            except Exception as e:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: parse error: {e}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            if not meeting_races:
                print(
                    f"paddy: skipping meeting {meeting_id} {anchor.venue}: no usable races",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            for r in meeting_races:
                ew = r.each_way_terms
                ew_str = (
                    f"eachway={ew.fraction:.2f} places={ew.places}"
                    if ew else "eachway=no"
                )
                print(f"  {r.off_time[11:16]} {r.venue} ({meeting_id}) "
                      f"→ {len(r.runners)} runners, {ew_str}")
            all_races.extend(meeting_races)

        if attempted > 0 and not all_races:
            # Every attempted meeting failed.
            print("paddy: every attempted meeting failed", file=sys.stderr)
            return 1

        all_races.sort(key=lambda r: r.off_time)
        _write(out_path, now, all_races)
        print(
            f"Wrote {out_path} ({len(all_races)} races from "
            f"{attempted - skipped} meetings, {skipped} skipped)"
        )
        return 0


def _group_by_meeting(stubs: Iterable[RaceStub]) -> dict[str, list[RaceStub]]:
    groups: dict[str, list[RaceStub]] = {}
    for s in stubs:
        groups.setdefault(s.meeting_id, []).append(s)
    for v in groups.values():
        v.sort(key=lambda s: s.start_time_utc)
    # Deterministic meeting order: earliest race first.
    return dict(sorted(groups.items(), key=lambda kv: kv[1][0].start_time_utc))


def _iso_utc(dt: datetime) -> str:
    s = dt.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return s.replace("+00:00", "Z")


def _write(out_path: Path, now: datetime, races: list[PaddyRace]) -> None:
    write_paddypower_json(
        PaddyOutput(scraped_at=_iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
```

- [ ] **Step 4: Run all tests to verify pass**

Run: `uv --project paddypower-py run pytest -v`
Expected: all unit tests pass; smoke test skipped (no RUN_INTEGRATION).

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/src/paddypower_scraper/cli.py paddypower-py/tests/test_cli.py
git commit -m "Add cli.py: orchestrate index → per-meeting fan-out → paddypower.json"
```

---

## Task 11: Live end-to-end smoke + Kotlin schema-validator contract test

**Files:**
- Modify: `paddypower-py/tests/test_output.py` (add contract test)

This task adds the cross-language contract test and runs the scraper end-to-end against live PaddyPower for one manual sanity check before wiring it into the pipeline.

- [ ] **Step 1: Add the contract test**

Append to `paddypower-py/tests/test_output.py`:

```python
import os
import subprocess


class TestKotlinValidatorContract:
    """Opt-in: shells out to the Kotlin PaddySchemaValidator to confirm
    Python output is byte-shape compatible with the arb finder.

    Run with: RUN_CONTRACT=1 uv run pytest -m contract"""

    pytestmark = [pytest.mark.contract]

    @pytest.mark.skipif(
        os.environ.get("RUN_CONTRACT") != "1",
        reason="set RUN_CONTRACT=1 to run cross-language contract test",
    )
    def test_sample_output_passes_kotlin_validator(self, tmp_path: Path):
        out = tmp_path / "paddypower.json"
        write_paddypower_json(_sample_output(), out)
        # Repo root: tests/ is two levels under repo
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["./gradlew", "run", "--quiet",
             "-PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt",
             f"--args={out}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"validator failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
```

You'll also need to add `import pytest` at the top of `test_output.py` if it isn't already there (the existing tests use the fixture, so `pytest` is implicit but the marker decorator and skipif need the explicit import).

Verify by looking at the top of the file:
```bash
head -5 paddypower-py/tests/test_output.py
```
If `import pytest` is missing, add it.

- [ ] **Step 2: Run the contract test**

Run: `RUN_CONTRACT=1 uv --project paddypower-py run pytest tests/test_output.py -m contract -v`
Expected: 1 passed (15-30s due to gradle boot).
If validator reports errors: the snake→camel map in `output.py` is missing a field. Fix and re-run.

- [ ] **Step 3: Live end-to-end smoke run**

Run:
```bash
uv --project paddypower-py run python -m paddypower_scraper gb-ie
```
Expected:
- stdout starts with `Fetching PaddyPower meetings for regions=gb-ie...`
- one progress line per race in the fanned-out meetings
- ends with `Wrote paddypower.json (N races from M meetings, S skipped)` where N > 0 on a normal racing day (0 OK at very late night / pre-dawn)
- exits 0
- `paddypower.json` exists at repo root

Confirm with:
```bash
python3 -c "import json; d=json.load(open('paddypower.json')); print('races:', d['raceCount'], 'sample:', d['races'][0]['venue'] if d['races'] else 'none')"
```

- [ ] **Step 4: Validate live output with the Kotlin validator**

Run:
```bash
./gradlew run --quiet -PmainClass=com.horsey.scraper.paddypower.PaddyValidateMainKt --args="paddypower.json"
```
Expected: exit 0, no errors printed.

- [ ] **Step 5: Commit**

```bash
git add paddypower-py/tests/test_output.py
git commit -m "Add Kotlin-validator contract test for Python paddypower.json output"
```

(No code changes from the live smoke run — just verification.)

---

## Task 12: Wire into run.sh, delete Kotlin PaddyPower scraper, full pipeline

**Files:**
- Modify: `run.sh`
- Delete: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt`
- Delete: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt`
- Delete: `src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt`
- Delete: `src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt`
- Modify: `src/main/kotlin/com/horsey/scraper/Main.kt` (remove PaddyPower phase)

- [ ] **Step 1: Replace `run.sh`**

Overwrite `run.sh` with:

```bash
#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: Kotlin Betfair scrape → Python PaddyPower scrape → Kotlin arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
REGIONS="${1:-gb-ie}"
./gradlew run --quiet --args="$REGIONS"
uv --project paddypower-py run python -m paddypower_scraper "$REGIONS"
exec ./gradlew run --quiet -PmainClass=com.horsey.scraper.arb.ArbMainKt
```

- [ ] **Step 2: Delete the Kotlin PaddyPower scraper files**

Run:
```bash
rm src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt
rm src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt
rm src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt
rm src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt
```

Confirm `PaddyModels.kt`, `PaddySchemaValidator.kt`, `PaddyValidateMain.kt`, `PaddySchemaValidatorTest.kt`, `PaddyValidateMainCliTest.kt` are still present:
```bash
ls src/main/kotlin/com/horsey/scraper/paddypower/ src/test/kotlin/com/horsey/scraper/paddypower/
```

- [ ] **Step 3: Edit `Main.kt` to remove the PaddyPower phase**

Open `src/main/kotlin/com/horsey/scraper/Main.kt` and locate the block that runs `PaddyNextRacesFetcher` (approx lines 113-128, starting at the comment `// ---------- PaddyPower phase ----------`).

Delete the entire `// ---------- PaddyPower phase ----------` block including:
- the section comment
- the `println("\nFetching PaddyPower next-races…")`
- the `try { … } catch { … }` invoking `PaddyNextRacesFetcher`
- the `File("paddypower.json").writeText(...)` line
- the final `println("Wrote paddypower.json …")`

Also remove any now-unused imports of `com.horsey.scraper.paddypower.PaddyNextRacesFetcher` and `com.horsey.scraper.paddypower.PaddyClient` at the top of the file (search and remove).

- [ ] **Step 4: Verify Kotlin compiles and tests pass**

Run: `./gradlew test`
Expected: BUILD SUCCESSFUL. Tests that were testing the deleted PaddyResponses code are gone with the file; remaining PaddyPower tests (`PaddySchemaValidatorTest`, `PaddyValidateMainCliTest`) still pass because they test files we kept.

If compile fails because of a leftover import: fix the import and re-run.

- [ ] **Step 5: Verify run.sh executable bit**

Run: `ls -l run.sh`
Expected: `-rwxr-xr-x` or similar with `x`. If not executable: `chmod +x run.sh`.

- [ ] **Step 6: Run the full pipeline end-to-end**

Run:
```bash
./run.sh gb-ie
```
Expected:
- Betfair phase prints its usual output and writes `betfair.json`
- PaddyPower phase prints its progress lines and writes `paddypower.json`
- Arb phase prints arb count and writes `arbs.json`
- exit 0

Confirm:
```bash
ls -la betfair.json paddypower.json arbs.json
python3 -c "import json; print('arbs:', json.load(open('arbs.json'))['arbCount'])"
```

- [ ] **Step 7: Commit**

```bash
git add run.sh src/main/kotlin/com/horsey/scraper/Main.kt
git rm src/main/kotlin/com/horsey/scraper/paddypower/PaddyClient.kt \
       src/main/kotlin/com/horsey/scraper/paddypower/PaddyNextRacesFetcher.kt \
       src/main/kotlin/com/horsey/scraper/paddypower/PaddyResponses.kt \
       src/test/kotlin/com/horsey/scraper/paddypower/PaddyResponsesTest.kt
git commit -m "$(cat <<'EOF'
Switch PaddyPower scraper to Python, drop Kotlin next-races implementation

run.sh now chains Kotlin Betfair → Python paddypower-py → Kotlin arb.
Kotlin PaddyClient/PaddyNextRacesFetcher/PaddyResponses and their tests
are deleted; PaddyModels + PaddySchemaValidator + PaddyValidateMain
stay because the arb finder still parses paddypower.json into the
Kotlin dataclasses and the validator now gates Python output.

Lifts today GB+IE coverage from ~2 races to ~18 (full day's card),
removes the stale-card-id and tomorrow-leak failure modes.
EOF
)"
```

---

## Done

All 12 tasks complete. The Python scraper owns PaddyPower; Kotlin owns Betfair + arb + the `paddypower.json` schema contract; `run.sh` orchestrates. To verify in future sessions:

- Unit tests: `cd paddypower-py && uv run pytest`
- Live: `RUN_INTEGRATION=1 uv --project paddypower-py run pytest -m integration`
- Contract: `RUN_CONTRACT=1 uv --project paddypower-py run pytest -m contract`
- Full pipeline: `./run.sh gb-ie`
