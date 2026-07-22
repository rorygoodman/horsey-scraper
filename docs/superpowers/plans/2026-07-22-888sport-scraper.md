# 888sport Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 888sport as a second bookie — scrape today's races into `888sport.json`, then price each-way arbs against the shared Betfair lay scrape into a separate `888horses.json`, leaving the PaddyPower path untouched.

**Architecture:** A new `sport888_scraper/` package mirrors `paddypower_scraper/` (index fetch → per-race fan-out → JSON), driven by 888's `getSchedule` + `getRacecard` endpoints. The arb finder is extended additively with a name+time matcher (`matching.py`), a `find_horses_by_name` join, and a `--source 888` CLI mode; the existing `find_horses`/default CLI path is unchanged.

**Tech Stack:** Python ≥3.11, Playwright (headless Chromium), pytest, `uv`.

## Global Constraints

- Python ≥ 3.11; no new third-party dependencies (Playwright + certifi only).
- New package name is `sport888_scraper` (Python identifiers cannot start with a digit); output **files** are `888sport.json` and `888horses.json`.
- Leave the PaddyPower path (`paddypower_scraper/`, `paddypower.json`, `arb_finder.find_horses`, `horses.json`), the web page, and `publish.sh` **unmodified**.
- Existing `python -m arb_finder` (no args) invocation must remain byte-for-byte unchanged in behavior.
- 888 API access requires session cookies from a warmup visit; `x-forwarded-for` is NOT needed. Endpoints:
  - Schedule: `https://spectate-web.888sport.com/spectate/racing/getSchedule/horse-racing?tab=today`
  - Racecard: `https://spectate-web.888sport.com/spectate/sportsbook-req/getRacecard/<eventId>`
- Region → 888 category slug: `gb-ie` → `uk-and-ireland`, `us` → `north-america`.
- Each-way terms: `fraction = 1 / place_odds_divisor`, `places = places_paid`; only when `allow_each_way == "1"`.
- Winner-market runners are `selections_details` entries with `market_id == "1"`.
- Test fixtures already exist (committed with this plan): `tests/fixtures/eight88_schedule.json` (real `getSchedule`, trimmed to `uk-and-ireland` + `north-america`) and `tests/fixtures/eight88_racecard.json` (real GB `getRacecard` for Worcester).
- Follow existing conventions: `from __future__ import annotations`; frozen dataclasses; snake_case internally, camelCase at the JSON boundary via `common.jsonio.write_json`; atomic writes; tests are flat in `tests/`, imported by module name (`pythonpath = ["src"]`).

---

## Prep: register test fixtures in conftest

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add two fixtures to `tests/conftest.py`** (append after `racing_page_payload`):

```python
@pytest.fixture
def eight88_schedule_payload() -> dict:
    """Raw 888 getSchedule?tab=today response (trimmed to UK&IRE + N.America)."""
    return _load("eight88_schedule.json")


@pytest.fixture
def eight88_racecard_payload() -> dict:
    """Raw 888 getRacecard response for a GB race (Worcester)."""
    return _load("eight88_racecard.json")
```

- [ ] **Step 2: Verify fixtures load**

Run: `uv run python -c "import json; json.load(open('tests/fixtures/eight88_schedule.json')); json.load(open('tests/fixtures/eight88_racecard.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py tests/fixtures/eight88_schedule.json tests/fixtures/eight88_racecard.json
git commit -m "test: add 888sport getSchedule + getRacecard fixtures"
```

---

## Task 1: Region → 888 category-slug map

**Files:**
- Create: `src/sport888_scraper/__init__.py` (empty)
- Create: `src/sport888_scraper/regions.py`
- Test: `tests/test_sport888_regions.py`

**Interfaces:**
- Consumes: `common.regions.parse_regions` (validates `gb-ie`/`us`).
- Produces: `REGION_SLUGS: dict[str, frozenset[str]]`; `slugs_for_all(region_ids: frozenset[str]) -> frozenset[str]`.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_regions.py`:

```python
from common.regions import parse_regions
from sport888_scraper.regions import REGION_SLUGS, slugs_for_all


def test_gb_ie_maps_to_uk_and_ireland():
    assert slugs_for_all(parse_regions("gb-ie")) == frozenset({"uk-and-ireland"})


def test_us_maps_to_north_america():
    assert slugs_for_all(parse_regions("us")) == frozenset({"north-america"})


def test_both_regions_union():
    assert slugs_for_all(parse_regions("gb-ie,us")) == frozenset(
        {"uk-and-ireland", "north-america"}
    )


def test_map_keys_match_region_ids():
    assert set(REGION_SLUGS) == {"gb-ie", "us"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_regions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sport888_scraper'`

- [ ] **Step 3: Create `src/sport888_scraper/__init__.py`** (empty file), then write `src/sport888_scraper/regions.py`:

```python
"""Region id → 888sport category slug(s). Pure, no I/O.

888's racing taxonomy groups by category slug, not Betfair country code:
`uk-and-ireland` covers GB+IE, `north-america` covers US (+Canada). This map
is 888-specific and deliberately separate from common.regions (country codes)."""

from __future__ import annotations

REGION_SLUGS: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"uk-and-ireland"}),
    "us": frozenset({"north-america"}),
}


def slugs_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of 888 category slugs for every region id. Assumes ids are
    valid (caller validates first via common.regions.parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_SLUGS.get(rid, frozenset())
    return frozenset(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_regions.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/__init__.py src/sport888_scraper/regions.py tests/test_sport888_regions.py
git commit -m "feat(888): region id -> category slug map"
```

---

## Task 2: Data models

**Files:**
- Create: `src/sport888_scraper/models.py`
- Test: `tests/test_sport888_models.py`

**Interfaces:**
- Produces:
  - `EachWayTerms(fraction: float, places: int)`
  - `Sport888Runner(name: str, win_price: float | None, win_price_raw: str | None)`
  - `Sport888Race(venue, country, off_time, market_name, scraped_at, each_way_terms: EachWayTerms | None, runners: list[Sport888Runner])`
  - `Sport888Output(scraped_at, race_count, races: list[Sport888Race])` with `from_dict`
  - `Sport888Stub(event_id, venue, category_slug, start_time_utc)` (internal, not serialized)

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_models.py`:

```python
from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)


def _sample() -> dict:
    return {
        "scrapedAt": "2026-07-22T12:00:00Z",
        "raceCount": 1,
        "races": [
            {
                "venue": "Worcester",
                "country": "uk-and-ireland",
                "offTime": "2026-07-22T12:55:00+00:00",
                "marketName": "Winner Market",
                "scrapedAt": "2026-07-22T12:00:00Z",
                "eachWayTerms": {"fraction": 0.2, "places": 3},
                "runners": [
                    {"name": "Holy Legend", "winPrice": 3.25, "winPriceRaw": "9/4"},
                    {"name": "No Price", "winPrice": None, "winPriceRaw": None},
                ],
            }
        ],
    }


def test_from_dict_roundtrips_fields():
    out = Sport888Output.from_dict(_sample())
    assert out.race_count == 1
    race = out.races[0]
    assert isinstance(race, Sport888Race)
    assert race.venue == "Worcester"
    assert race.country == "uk-and-ireland"
    assert race.off_time == "2026-07-22T12:55:00+00:00"
    assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)
    assert race.runners[0] == Sport888Runner("Holy Legend", 3.25, "9/4")
    assert race.runners[1] == Sport888Runner("No Price", None, None)


def test_from_dict_null_each_way_terms():
    d = _sample()
    d["races"][0]["eachWayTerms"] = None
    assert Sport888Output.from_dict(d).races[0].each_way_terms is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_models.py -q`
Expected: FAIL — `ImportError`/`ModuleNotFoundError`

- [ ] **Step 3: Write `src/sport888_scraper/models.py`**:

```python
"""Dataclasses mirroring 888sport.json. snake_case here; the
snake→camel conversion happens in output.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EachWayTerms:
    fraction: float
    places: int

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "EachWayTerms":
        return cls(fraction=d["fraction"], places=d["places"])


@dataclass(frozen=True)
class Sport888Runner:
    name: str
    win_price: float | None
    win_price_raw: str | None

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Runner":
        return cls(
            name=d["name"],
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )


@dataclass(frozen=True)
class Sport888Race:
    venue: str
    country: str  # 888 category slug, e.g. "uk-and-ireland"
    off_time: str
    market_name: str
    scraped_at: str
    each_way_terms: EachWayTerms | None
    runners: list[Sport888Runner] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Race":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            scraped_at=d["scrapedAt"],
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[Sport888Runner.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class Sport888Output:
    scraped_at: str
    race_count: int
    races: list[Sport888Race] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "Sport888Output":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[Sport888Race.from_dict(r) for r in d.get("races", [])],
        )


@dataclass(frozen=True)
class Sport888Stub:
    """Internal: metadata-only race entry from the schedule index.
    Not emitted in 888sport.json."""
    event_id: str
    venue: str
    category_slug: str
    start_time_utc: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_models.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/models.py tests/test_sport888_models.py
git commit -m "feat(888): data models mirroring 888sport.json"
```

---

## Task 3: API endpoint URLs

**Files:**
- Create: `src/sport888_scraper/api.py`
- Test: `tests/test_sport888_api.py`

**Interfaces:**
- Produces: `USER_AGENT`, `LOCALE`, `TIMEZONE`, `WARMUP_URL`, `SCHEDULE_URL` constants; `racecard_url(event_id: str) -> str`.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_api.py`:

```python
from sport888_scraper import api


def test_schedule_url_is_today_tab():
    assert api.SCHEDULE_URL.endswith("getSchedule/horse-racing?tab=today")
    assert api.SCHEDULE_URL.startswith("https://spectate-web.888sport.com/")


def test_racecard_url_embeds_event_id():
    url = api.racecard_url("7960079")
    assert url == (
        "https://spectate-web.888sport.com/spectate/sportsbook-req/"
        "getRacecard/7960079"
    )


def test_warmup_url_is_888sport():
    assert api.WARMUP_URL.startswith("https://www.888sport.com/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_api.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/api.py`**:

```python
"""888sport (spectate) endpoint constants and URL builders. No I/O."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-GB"
TIMEZONE = "Europe/London"

# Warmup page — seeds the session cookies the spectate API requires
# (bare requests without cookies get 403).
WARMUP_URL = "https://www.888sport.com/horse-racing/"

# Full-day meetings index, grouped category → meeting → event ids.
SCHEDULE_URL = (
    "https://spectate-web.888sport.com/spectate/racing/"
    "getSchedule/horse-racing?tab=today"
)

_RACECARD_BASE = (
    "https://spectate-web.888sport.com/spectate/sportsbook-req/getRacecard/"
)


def racecard_url(event_id: str) -> str:
    """Build a getRacecard URL for one 888 event id."""
    return f"{_RACECARD_BASE}{quote(event_id, safe='')}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_api.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/api.py tests/test_sport888_api.py
git commit -m "feat(888): API endpoint constants + racecard URL builder"
```

---

## Task 4: Schedule (meetings index) parser

**Files:**
- Create: `src/sport888_scraper/schedule.py`
- Test: `tests/test_sport888_schedule.py`

**Interfaces:**
- Consumes: `Sport888Stub` (Task 2); the `eight88_schedule_payload` fixture.
- Produces: `parse_schedule(payload: dict) -> list[Sport888Stub]` — one stub per `event_details` entry with all required fields; silently drops incomplete entries; region filtering happens later in the CLI.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_schedule.py`:

```python
import copy

from sport888_scraper.models import Sport888Stub
from sport888_scraper.schedule import parse_schedule


class TestParseSchedule:
    def test_returns_stubs(self, eight88_schedule_payload):
        stubs = parse_schedule(eight88_schedule_payload)
        assert stubs, "fixture should yield stubs"
        assert all(isinstance(s, Sport888Stub) for s in stubs)

    def test_includes_uk_and_ireland(self, eight88_schedule_payload):
        stubs = parse_schedule(eight88_schedule_payload)
        slugs = {s.category_slug for s in stubs}
        assert "uk-and-ireland" in slugs
        worcester = [s for s in stubs if s.venue == "Worcester"]
        assert worcester
        assert worcester[0].start_time_utc.startswith("2026-07-22T")
        assert worcester[0].event_id  # non-empty

    def test_field_types(self, eight88_schedule_payload):
        for s in parse_schedule(eight88_schedule_payload):
            for f in ("event_id", "venue", "category_slug", "start_time_utc"):
                v = getattr(s, f)
                assert isinstance(v, str) and v, f"{f} bad: {v!r}"

    def test_drops_entry_missing_scheduled_start(self, eight88_schedule_payload):
        p = copy.deepcopy(eight88_schedule_payload)
        victim = next(iter(p["event_details"]))
        p["event_details"][victim].pop("scheduled_start", None)
        stubs = parse_schedule(p)
        assert all(s.event_id != str(victim) for s in stubs)

    def test_empty_payload(self):
        assert parse_schedule({}) == []
        assert parse_schedule({"event_details": {}}) == []

    def test_returns_list(self, eight88_schedule_payload):
        assert isinstance(parse_schedule(eight88_schedule_payload), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_schedule.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/schedule.py`**:

```python
"""Parse the getSchedule?tab=today response into race stubs.

The response groups the whole day category → meeting → event ids, but every
event's flat metadata lives under `event_details[<eventId>]`. We read that map
directly (venue name, scheduled_start, category_slug) — region filtering is the
CLI's job, so this returns every well-formed stub regardless of region."""

from __future__ import annotations

from .models import Sport888Stub


def parse_schedule(payload: dict) -> list[Sport888Stub]:
    """One Sport888Stub per event_details entry that has all of: id, name
    (venue), category_slug, scheduled_start. Drops anything incomplete."""
    event_details = payload.get("event_details") if isinstance(payload, dict) else None
    if not isinstance(event_details, dict):
        return []
    out: list[Sport888Stub] = []
    for entry in event_details.values():
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        eid = str(eid) if isinstance(eid, (str, int)) and str(eid) else None
        venue = entry.get("name")
        slug = entry.get("category_slug")
        start = entry.get("scheduled_start")
        if not (eid and isinstance(venue, str) and venue
                and isinstance(slug, str) and slug
                and isinstance(start, str) and start):
            continue
        out.append(Sport888Stub(
            event_id=eid, venue=venue, category_slug=slug, start_time_utc=start,
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_schedule.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/schedule.py tests/test_sport888_schedule.py
git commit -m "feat(888): getSchedule parser -> race stubs"
```

---

## Task 5: Racecard parser

**Files:**
- Create: `src/sport888_scraper/racecard.py`
- Test: `tests/test_sport888_racecard.py`

**Interfaces:**
- Consumes: `EachWayTerms`, `Sport888Race`, `Sport888Runner` (Task 2); the `eight88_racecard_payload` fixture.
- Produces: `parse_racecard(payload: dict, scraped_at_utc: str) -> Sport888Race | None`. Returns None when the racecard has no event, no venue/start, or no usable runners. Only `market_id == "1"` (Winner Market) runners are kept. Each-way terms only when `allow_each_way == "1"`. Price parity: `win_price`/`win_price_raw` both set or both None.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_racecard.py`:

```python
import copy

from sport888_scraper.models import EachWayTerms, Sport888Race
from sport888_scraper.racecard import parse_racecard

SCRAPED = "2026-07-22T12:00:00Z"


class TestParseRacecard:
    def test_parses_worcester(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        assert isinstance(race, Sport888Race)
        assert race.venue == "Worcester"
        assert race.country == "uk-and-ireland"
        assert race.off_time == "2026-07-22T12:55:00+00:00"
        assert race.scraped_at == SCRAPED
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)

    def test_runner_prices(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        by_name = {r.name: r for r in race.runners}
        holy = by_name["Holy Legend"]
        assert holy.win_price == 3.25
        assert holy.win_price_raw == "9/4"
        # every runner obeys price parity
        for r in race.runners:
            assert (r.win_price is None) == (r.win_price_raw is None)

    def test_only_winner_market_runners(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        # 8 winner-market runners in the fixture
        assert len(race.runners) == 8

    def test_no_each_way_when_flag_off(self, eight88_racecard_payload):
        p = copy.deepcopy(eight88_racecard_payload)
        eid = next(iter(p["racecard"]["each_way_terms"]))
        p["racecard"]["each_way_terms"][eid]["allow_each_way"] = "0"
        race = parse_racecard(p, SCRAPED)
        assert race.each_way_terms is None

    def test_returns_none_when_no_events(self):
        assert parse_racecard({"racecard": {"events": {}}}, SCRAPED) is None
        assert parse_racecard({}, SCRAPED) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_racecard.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/racecard.py`**:

```python
"""Parse a getRacecard response into one Sport888Race.

Winner-market runners are `selections_details` entries with market_id == "1".
Each-way terms come from `each_way_terms[<eventId>]` when allow_each_way == "1"
(fraction = 1 / place_odds_divisor, places = places_paid)."""

from __future__ import annotations

from .models import EachWayTerms, Sport888Race, Sport888Runner

WINNER_MARKET_ID = "1"


def parse_racecard(payload: dict, scraped_at_utc: str) -> "Sport888Race | None":
    rc = payload.get("racecard") if isinstance(payload, dict) else None
    if not isinstance(rc, dict):
        return None
    events = rc.get("events")
    if not isinstance(events, dict) or not events:
        return None
    event_id, event = next(iter(events.items()))
    details = event.get("details") if isinstance(event, dict) else None
    if not isinstance(details, dict):
        return None
    venue = details.get("name")
    start = details.get("scheduled_start")
    if not (isinstance(venue, str) and venue and isinstance(start, str) and start):
        return None
    runners = _parse_runners(rc.get("selections_details"))
    if not runners:
        return None
    return Sport888Race(
        venue=venue,
        country=details.get("category_slug") or "",
        off_time=start,  # already an ISO offset string, e.g. "...+00:00"
        market_name="Winner Market",
        scraped_at=scraped_at_utc,
        each_way_terms=_parse_eachway(rc.get("each_way_terms"), str(event_id)),
        runners=runners,
    )


def _parse_eachway(terms: object, event_id: str) -> "EachWayTerms | None":
    if not isinstance(terms, dict):
        return None
    t = terms.get(event_id)
    if not isinstance(t, dict) or t.get("allow_each_way") != "1":
        return None
    try:
        divisor = int(t["place_odds_divisor"])
        places = int(t["places_paid"])
    except (KeyError, TypeError, ValueError):
        return None
    if divisor <= 0 or places <= 0:
        return None
    fraction = 1.0 / divisor
    if not (0.0 < fraction <= 1.0):
        return None
    return EachWayTerms(fraction=fraction, places=places)


def _parse_runners(sels: object) -> list[Sport888Runner]:
    if not isinstance(sels, dict):
        return []
    out: list[Sport888Runner] = []
    for s in sels.values():
        if not isinstance(s, dict) or s.get("market_id") != WINNER_MARKET_ID:
            continue
        name = s.get("name")
        if not isinstance(name, str) or not name:
            continue
        price = _to_float(s.get("decimal_price"))
        raw = s.get("fraction_price")
        raw = raw if isinstance(raw, str) and raw else None
        active = s.get("active") == "1"
        betable = s.get("betable") is True
        if not (active and betable) or price is None or price <= 0.0 or raw is None:
            price = None
            raw = None
        out.append(Sport888Runner(name=name, win_price=price, win_price_raw=raw))
    return out


def _to_float(v: object) -> "float | None":
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_racecard.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/racecard.py tests/test_sport888_racecard.py
git commit -m "feat(888): getRacecard parser -> Sport888Race"
```

---

## Task 6: Output serializer

**Files:**
- Create: `src/sport888_scraper/output.py`
- Test: `tests/test_sport888_output.py`

**Interfaces:**
- Consumes: `Sport888Output` (Task 2), `common.jsonio.write_json`.
- Produces: `SPORT888_RENAME: dict[str, str]`; `write_sport888_json(out: Sport888Output, path) -> None`.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_output.py`:

```python
import json

from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from sport888_scraper.output import write_sport888_json


def _out() -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:00Z",
        race_count=1,
        races=[Sport888Race(
            venue="Worcester", country="uk-and-ireland",
            off_time="2026-07-22T12:55:00+00:00", market_name="Winner Market",
            scraped_at="2026-07-22T12:00:00Z",
            each_way_terms=EachWayTerms(0.2, 3),
            runners=[Sport888Runner("Holy Legend", 3.25, "9/4")],
        )],
    )


def test_writes_camelcase(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["offTime"] == "2026-07-22T12:55:00+00:00"
    assert race["marketName"] == "Winner Market"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    r = race["runners"][0]
    assert r["winPrice"] == 3.25 and r["winPriceRaw"] == "9/4"


def test_no_betfair_ids_in_output(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_out(), p)
    text = p.read_text()
    assert "betfair" not in text.lower()
    assert "selectionId" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_output.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/output.py`**:

```python
"""Serialize Sport888Output to 888sport.json with camelCase keys, atomic
write. Delegates to common.jsonio.write_json."""

from __future__ import annotations

from pathlib import Path

from common.jsonio import write_json

from .models import Sport888Output

SPORT888_RENAME = {
    "each_way_terms": "eachWayTerms",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "off_time": "offTime",
    "market_name": "marketName",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_sport888_json(out: Sport888Output, path: Path | str) -> None:
    write_json(out, SPORT888_RENAME, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_output.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/output.py tests/test_sport888_output.py
git commit -m "feat(888): 888sport.json serializer"
```

---

## Task 7: Schema validation + validate CLI

**Files:**
- Create: `src/sport888_scraper/validation.py`
- Create: `src/sport888_scraper/validate.py`
- Test: `tests/test_sport888_validation.py`

**Interfaces:**
- Consumes: `common.isovalid.is_iso_utc`, `is_iso_offset_datetime`; `write_sport888_json` (round-trip guard).
- Produces: `validate_sport888_output(text: str) -> list[str]` ([] when valid); `sport888_scraper.validate.main(argv) -> int`.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_validation.py`:

```python
import json

from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from sport888_scraper.output import write_sport888_json
from sport888_scraper.validation import validate_sport888_output


def _valid_output() -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:00Z", race_count=1,
        races=[Sport888Race(
            venue="Worcester", country="uk-and-ireland",
            off_time="2026-07-22T12:55:00+00:00", market_name="Winner Market",
            scraped_at="2026-07-22T12:00:00Z", each_way_terms=EachWayTerms(0.2, 3),
            runners=[Sport888Runner("Holy Legend", 3.25, "9/4"),
                     Sport888Runner("No Price", None, None)],
        )],
    )


def test_serialized_output_is_valid(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_valid_output(), p)
    assert validate_sport888_output(p.read_text()) == []


def test_race_count_mismatch_flagged():
    d = json.loads(_dump(_valid_output()))
    d["raceCount"] = 99
    errs = validate_sport888_output(json.dumps(d))
    assert any("raceCount" in e for e in errs)


def test_price_parity_violation_flagged():
    d = json.loads(_dump(_valid_output()))
    d["races"][0]["runners"][0]["winPriceRaw"] = None  # price set, raw null
    errs = validate_sport888_output(json.dumps(d))
    assert any("parity" in e.lower() for e in errs)


def test_bad_offtime_flagged():
    d = json.loads(_dump(_valid_output()))
    d["races"][0]["offTime"] = "not-a-date"
    errs = validate_sport888_output(json.dumps(d))
    assert any("offTime" in e for e in errs)


def test_not_json():
    assert validate_sport888_output("{not json") != []


def _dump(out: Sport888Output) -> str:
    from common.jsonio import to_camel_dict
    from sport888_scraper.output import SPORT888_RENAME
    return json.dumps(to_camel_dict(out, SPORT888_RENAME))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_validation.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/validation.py`**:

```python
"""Validate an 888sport.json payload string against the schema.

Returns [] when valid, else a list of human-readable error strings. Mirrors
paddypower_scraper.validation but drops raceUrl / betfairWinMarketId (888 has
no Betfair ids)."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(1, 7)


def validate_sport888_output(text: str) -> list[str]:
    errors: list[str] = []
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        return [f"not valid JSON object: {e}"]

    _require_str(root, "scrapedAt", errors,
                 lambda v: None if is_iso_utc(v)
                 else errors.append(f"top-level scrapedAt is not ISO-8601 UTC instant: '{v}'"))
    race_count = _require_int(root, "raceCount", errors)
    races = root.get("races")
    if not isinstance(races, list):
        errors.append("races: missing or not array")
        return errors
    if race_count is not None and race_count != len(races):
        errors.append(f"raceCount ({race_count}) != races.length ({len(races)})")

    for i, race in enumerate(races):
        ctx = f"races[{i}]"
        if not isinstance(race, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(race, "venue", errors)
        _require_str(race, "country", errors)
        _require_str(race, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(race, "marketName", errors)
        _require_str(race, "scrapedAt", errors,
                     lambda v: None if is_iso_utc(v)
                     else errors.append(f"{ctx}.scrapedAt not ISO-8601 UTC: '{v}'"))

        ew = race.get("eachWayTerms")
        if ew is not None:
            if not isinstance(ew, dict):
                errors.append(f"{ctx}.eachWayTerms: not an object or null")
            else:
                frac = ew.get("fraction")
                if not isinstance(frac, (int, float)) or isinstance(frac, bool) \
                        or not (0.0 < float(frac) <= 1.0):
                    errors.append(f"{ctx}.eachWayTerms.fraction must be in (0,1], got {frac}")
                places = ew.get("places")
                if not isinstance(places, int) or isinstance(places, bool) \
                        or places not in _EW_PLACES:
                    errors.append(f"{ctx}.eachWayTerms.places must be in {_EW_PLACES}, got {places}")

        runners = race.get("runners")
        if not isinstance(runners, list):
            errors.append(f"{ctx}.runners: missing or not array")
            continue
        for j, r in enumerate(runners):
            rctx = f"{ctx}.runners[{j}]"
            if not isinstance(r, dict):
                errors.append(f"{rctx}: not an object")
                continue
            _require_str(r, "name", errors)
            wp = r.get("winPrice")
            raw = r.get("winPriceRaw")
            if (wp is None) != (raw is None):
                errors.append(
                    f"{rctx}: price parity violation — winPrice null={wp is None}, "
                    f"winPriceRaw null={raw is None}"
                )
            if wp is not None and (not isinstance(wp, (int, float)) or isinstance(wp, bool)):
                errors.append(f"{rctx}.winPrice: not a number")
            if raw is not None and not isinstance(raw, str):
                errors.append(f"{rctx}.winPriceRaw: not a string")
    return errors


def _require_str(obj: dict, key: str, errors: list[str], extra=None) -> "str | None":
    v = obj.get(key)
    if not isinstance(v, str):
        errors.append(f"{key}: missing or not string")
        return None
    if extra is not None:
        extra(v)
    return v


def _require_int(obj: dict, key: str, errors: list[str]) -> "int | None":
    v = obj.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        errors.append(f"{key}: missing or not number")
        return None
    return v
```

- [ ] **Step 4: Write `src/sport888_scraper/validate.py`**:

```python
"""CLI: validate an 888sport.json file. `python -m sport888_scraper.validate <path>`."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_sport888_output


def main(argv: "list[str] | None" = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python -m sport888_scraper.validate <888sport.json>",
              file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text()
    except OSError as e:
        print(f"cannot read {argv[0]}: {e}", file=sys.stderr)
        return 2
    errors = validate_sport888_output(text)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sport888_validation.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add src/sport888_scraper/validation.py src/sport888_scraper/validate.py tests/test_sport888_validation.py
git commit -m "feat(888): 888sport.json schema validator + validate CLI"
```

---

## Task 8: Browser session

**Files:**
- Create: `src/sport888_scraper/browser.py`
- Test: `tests/test_sport888_browser_smoke.py`

**Interfaces:**
- Consumes: `sport888_scraper.api` constants; Playwright.
- Produces: `BrowserFetchError(url, reason)`; `BrowserSession` context manager with `fetch_json(url, timeout_ms=20_000) -> dict`.

Note: this mirrors `paddypower_scraper/browser.py` but warms up 888's page and reads its constants from `sport888_scraper.api`. Kept as a separate module so the 888 package does not import PaddyPower internals (deliberate, small duplication).

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_browser_smoke.py`:

```python
import pytest

from sport888_scraper.browser import BrowserFetchError, BrowserSession


def test_fetch_before_enter_raises():
    session = BrowserSession()
    with pytest.raises(RuntimeError):
        session.fetch_json("https://example.com")


def test_browser_fetch_error_carries_reason():
    e = BrowserFetchError("https://x", "HTTP 500")
    assert e.url == "https://x"
    assert e.reason == "HTTP 500"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_browser_smoke.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/browser.py`**:

```python
"""Playwright-driven browser session for 888sport (spectate) calls.

One BrowserSession per scraper run. Warms up once on __enter__ to seed the
session cookies the spectate API requires, then reuses the same context for
every fetch_json call."""

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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_browser_smoke.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/sport888_scraper/browser.py tests/test_sport888_browser_smoke.py
git commit -m "feat(888): headless-Chromium browser session"
```

---

## Task 9: CLI orchestration

**Files:**
- Create: `src/sport888_scraper/cli.py`
- Create: `src/sport888_scraper/__main__.py`
- Test: `tests/test_sport888_cli.py`

**Interfaces:**
- Consumes: `api` (Task 3), `browser.BrowserFetchError` (Task 8), `parse_schedule` (Task 4), `parse_racecard` (Task 5), `slugs_for_all` (Task 1), `write_sport888_json` (Task 6), `common.regions.parse_regions`, `common.timeutil.iso_utc`, and `london_day_window`/`in_window` from `paddypower_scraper.filtering` (pure, reused).
- Produces: `sport888_scraper.cli.main(argv=None, *, now_utc=None, make_session=..., out_path="888sport.json") -> int` (0 ok/partial/empty, 1 fetch error, 2 bad args). `__main__` calls it.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_cli.py`:

```python
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sport888_scraper import api, cli
from sport888_scraper.browser import BrowserFetchError


class FakeSession:
    def __init__(self, responses, errors=None):
        self.responses = responses
        self.errors = errors or {}
        self.calls: list[str] = []

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.calls.append(url)
        if url in self.errors:
            raise BrowserFetchError(url, self.errors[url])
        if url not in self.responses:
            raise AssertionError(f"unexpected URL: {url}")
        return self.responses[url]


def make_factory(session):
    @contextmanager
    def _factory():
        yield session
    return _factory


NOW = datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc)


def _schedule(events: list[dict]) -> dict:
    return {"event_details": {e["id"]: e for e in events}}


def _event(eid, name, slug, start):
    return {"id": eid, "name": name, "category_slug": slug,
            "scheduled_start": start}


def _racecard(eid, name, slug, start, runners):
    return {"racecard": {
        "events": {eid: {"details": {
            "id": eid, "name": name, "category_slug": slug,
            "scheduled_start": start}}},
        "each_way_terms": {eid: {"allow_each_way": "1",
                                 "place_odds_divisor": "5", "places_paid": "3"}},
        "selections_details": {
            f"{eid}_{i}": {"name": rn, "market_id": "1", "active": "1",
                           "betable": True, "decimal_price": "4.000",
                           "fraction_price": "3/1"}
            for i, rn in enumerate(runners)},
    }}


def test_happy_path_writes_json(tmp_path: Path):
    ev = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([ev]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], now_utc=NOW,
                  make_session=make_factory(FakeSession(responses)), out_path=out)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 1
    assert data["races"][0]["venue"] == "Worcester"
    assert data["races"][0]["runners"][0]["name"] == "Holy Legend"


def test_region_filter_excludes_us_from_gb_ie(tmp_path: Path):
    gb = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    us = _event("222", "Belmont", "north-america", "2026-07-22T20:00:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([gb, us]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    session = FakeSession(responses)
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 0
    assert [u for u in session.calls if "getRacecard" in u] == [api.racecard_url("111")]


def test_index_fetch_fails_exits_1(tmp_path: Path):
    session = FakeSession({}, {api.SCHEDULE_URL: "HTTP 503"})
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 1


def test_empty_day_writes_empty_exits_0(tmp_path: Path):
    session = FakeSession({api.SCHEDULE_URL: _schedule([])})
    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=out)
    assert rc == 0
    assert json.loads(out.read_text())["raceCount"] == 0


def test_all_races_fail_exits_1(tmp_path: Path):
    ev = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    session = FakeSession({api.SCHEDULE_URL: _schedule([ev])},
                          {api.racecard_url("111"): "HTTP 500"})
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 1


def test_bad_region_exits_2(tmp_path: Path):
    session = FakeSession({})
    rc = cli.main(["xx"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 2


def test_tomorrow_race_excluded(tmp_path: Path):
    today = _event("111", "Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00")
    tomorrow = _event("222", "Naas", "uk-and-ireland", "2026-07-23T18:00:00+00:00")
    responses = {
        api.SCHEDULE_URL: _schedule([today, tomorrow]),
        api.racecard_url("111"): _racecard(
            "111", "Worcester", "uk-and-ireland",
            "2026-07-22T12:55:00+00:00", ["Holy Legend"]),
    }
    session = FakeSession(responses)
    rc = cli.main(["gb-ie"], now_utc=NOW, make_session=make_factory(session),
                  out_path=tmp_path / "888sport.json")
    assert rc == 0
    assert [u for u in session.calls if "getRacecard" in u] == [api.racecard_url("111")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_cli.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write `src/sport888_scraper/cli.py`**:

```python
"""Top-level orchestration for the 888sport scraper. Pure functions
everywhere except the BrowserSession side effect, which is injectable."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from common.regions import parse_regions
from common.timeutil import iso_utc
from paddypower_scraper.filtering import in_window, london_day_window

from . import api
from .browser import BrowserFetchError, BrowserSession
from .models import Sport888Output, Sport888Race
from .output import write_sport888_json
from .racecard import parse_racecard
from .regions import slugs_for_all
from .schedule import parse_schedule


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("888sport.json"),
) -> int:
    """Return exit code (0 = success/partial/empty, 1 = fetch error, 2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        wanted_slugs = slugs_for_all(parse_regions(region_arg))
    except ValueError as e:
        print(f"sport888-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching 888sport schedule for regions={region_arg}...")

    with make_session() as session:
        try:
            index_payload = session.fetch_json(api.SCHEDULE_URL)
        except BrowserFetchError as e:
            print(f"888: schedule fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_schedule(index_payload)
        in_region = [s for s in stubs if s.category_slug in wanted_slugs]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        if not in_today:
            _write(out_path, now, [])
            print(f"Wrote {out_path} (0 races, 0 skipped)")
            return 0

        in_today.sort(key=lambda s: s.start_time_utc)

        races: list[Sport888Race] = []
        attempted = 0
        skipped = 0
        for stub in in_today:
            attempted += 1
            url = api.racecard_url(stub.event_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                race = parse_racecard(payload, scraped_at)
            except BrowserFetchError as e:
                print(f"888: skipping race {stub.event_id} {stub.venue}: {e.reason}",
                      file=sys.stderr)
                skipped += 1
                continue
            except Exception as e:
                print(f"888: skipping race {stub.event_id} {stub.venue}: parse error: {e}",
                      file=sys.stderr)
                skipped += 1
                continue
            if race is None:
                print(f"888: skipping race {stub.event_id} {stub.venue}: no usable race",
                      file=sys.stderr)
                skipped += 1
                continue
            races.append(race)

        if attempted > 0 and not races:
            print("888: every attempted race failed", file=sys.stderr)
            return 1

        seen: set[tuple[str, str]] = set()
        deduped: list[Sport888Race] = []
        for r in races:
            key = (r.venue, r.off_time)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r.off_time)

        for r in deduped:
            ew = r.each_way_terms
            ew_str = (f"eachway={ew.fraction:.2f} places={ew.places}"
                      if ew else "eachway=no")
            print(f"  {r.off_time[11:16]} {r.venue} → {len(r.runners)} runners, {ew_str}")

        meetings = len({r.venue for r in deduped})
        _write(out_path, now, deduped)
        print(f"Wrote {out_path} ({len(deduped)} races from {meetings} "
              f"meetings, {skipped} skipped)")
        return 0


def _write(out_path: Path, now: datetime, races: list[Sport888Race]) -> None:
    write_sport888_json(
        Sport888Output(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
```

- [ ] **Step 4: Write `src/sport888_scraper/__main__.py`**:

```python
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sport888_cli.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add src/sport888_scraper/cli.py src/sport888_scraper/__main__.py tests/test_sport888_cli.py
git commit -m "feat(888): CLI orchestration (schedule index -> per-race fan-out)"
```

---

## Task 10: Name + time matcher

**Files:**
- Create: `src/arb_finder/matching.py`
- Test: `tests/test_matching.py`

**Interfaces:**
- Consumes: `betfair_scraper.models.RaceOdds`, `RunnerOdds`.
- Produces:
  - `normalize_name(name: str) -> str`, `normalize_venue(venue: str) -> str`
  - `to_instant(iso: str) -> datetime | None`
  - `match_race(off_time: str, venue: str, betfair_races: list[RaceOdds]) -> RaceOdds | None`
  - `match_runner(name: str, race: RaceOdds) -> RunnerOdds | None`

- [ ] **Step 1: Write the failing test** — `tests/test_matching.py`:

```python
from betfair_scraper.models import RaceOdds, RunnerOdds
from common.markettype import MarketType
from arb_finder.matching import (
    match_race,
    match_runner,
    normalize_name,
    normalize_venue,
    to_instant,
)


def _race(venue, off_time, runners) -> RaceOdds:
    return RaceOdds(
        race_id="1.1", venue=venue, country="GB", off_time=off_time,
        win_market_url="u", market_name="m",
        market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z"},
        runners=runners)


class TestNormalize:
    def test_name_strips_case_punct_space(self):
        assert normalize_name("O'Brien's Pride") == normalize_name("obriens pride")

    def test_name_folds_accents(self):
        assert normalize_name("Fánchén") == normalize_name("Fanchen")

    def test_venue_strips_suffix_punct(self):
        assert normalize_venue("Newmarket (July)") == "newmarketjuly"
        assert normalize_venue("Worcester") == "worcester"


class TestToInstant:
    def test_same_instant_across_offsets(self):
        assert to_instant("2026-07-22T12:55:00+00:00") == to_instant("2026-07-22T13:55:00+01:00")

    def test_z_suffix(self):
        assert to_instant("2026-07-22T12:55:00Z") == to_instant("2026-07-22T12:55:00+00:00")

    def test_bad_input(self):
        assert to_instant("nope") is None


class TestMatchRace:
    def test_venue_and_instant_match(self):
        bf = [_race("Worcester", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Worcester", bf)
        assert got is bf[0]

    def test_venue_drift_falls_back_to_unique_instant(self):
        bf = [_race("Worcester (AW)", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Worcester", bf)
        assert got is bf[0]

    def test_no_match_when_instant_absent(self):
        bf = [_race("Worcester", "2026-07-22T14:00:00+01:00", [])]
        assert match_race("2026-07-22T12:55:00+00:00", "Worcester", bf) is None

    def test_two_venues_same_instant_no_venue_match_is_ambiguous(self):
        bf = [_race("Ascot", "2026-07-22T13:55:00+01:00", []),
              _race("Naas", "2026-07-22T13:55:00+01:00", [])]
        assert match_race("2026-07-22T12:55:00+00:00", "Worcester", bf) is None

    def test_two_venues_same_instant_venue_disambiguates(self):
        bf = [_race("Ascot", "2026-07-22T13:55:00+01:00", []),
              _race("Naas", "2026-07-22T13:55:00+01:00", [])]
        got = match_race("2026-07-22T12:55:00+00:00", "Naas", bf)
        assert got.venue == "Naas"


class TestMatchRunner:
    def test_exact_normalized_match(self):
        race = _race("Worcester", "2026-07-22T13:55:00+01:00",
                     [RunnerOdds("Holy Legend", {MarketType.WIN: 4.0}, 1)])
        got = match_runner("Holy Legend", race)
        assert got.selection_id == 1

    def test_no_match_returns_none(self):
        race = _race("Worcester", "2026-07-22T13:55:00+01:00",
                     [RunnerOdds("Holy Legend", {MarketType.WIN: 4.0}, 1)])
        assert match_runner("Different Horse", race) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_matching.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'arb_finder.matching'`

- [ ] **Step 3: Write `src/arb_finder/matching.py`**:

```python
"""Structural match of a bookie race/runner to a Betfair race/runner.

888sport carries no Betfair ids, so we match by off-time instant + normalized
venue (race) and normalized runner name (selection). Exact normalized matches
only — no fuzzy matching, because a wrong match yields a silently mispriced arb."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from betfair_scraper.models import RaceOdds, RunnerOdds


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def normalize_name(name: str) -> str:
    """Lowercase, strip accents to ASCII, drop all non-alphanumerics."""
    return _fold(name)


def normalize_venue(venue: str) -> str:
    """Same folding as names — drops '(AW)', '(July)', spaces, punctuation."""
    return _fold(venue)


def to_instant(iso: str) -> "datetime | None":
    """Parse an ISO string to a UTC datetime, or None if unparseable."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def match_race(
    off_time: str, venue: str, betfair_races: list[RaceOdds]
) -> "RaceOdds | None":
    """Match by off-time instant + normalized venue. Falls back to the unique
    Betfair race at that instant when venue names disagree. Returns None when
    no candidate or when ambiguous."""
    inst = to_instant(off_time)
    if inst is None:
        return None
    same = [r for r in betfair_races if to_instant(r.off_time) == inst]
    if not same:
        return None
    v = normalize_venue(venue)
    vmatch = [r for r in same if normalize_venue(r.venue) == v]
    if len(vmatch) == 1:
        return vmatch[0]
    if not vmatch and len(same) == 1:
        return same[0]
    return None


def match_runner(name: str, race: RaceOdds) -> "RunnerOdds | None":
    """Match a runner by exact normalized name. None if absent or ambiguous."""
    n = normalize_name(name)
    matches = [r for r in race.runners if normalize_name(r.name) == n]
    return matches[0] if len(matches) == 1 else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_matching.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add src/arb_finder/matching.py tests/test_matching.py
git commit -m "feat(arb): name+time matcher for id-less bookies"
```

---

## Task 11: 888 arb output models

**Files:**
- Modify: `src/arb_finder/models.py`
- Test: `tests/test_horses888_models.py`

**Interfaces:**
- Consumes: existing `Runner`, `BetfairLayLeg` (arb_finder.models); `sport888_scraper.models.EachWayTerms`; `common.jsonio.write_json`.
- Produces:
  - `Sport888PriceLeg(win_price: float, win_price_raw: str, each_way_terms)`
  - `Horse888(venue, country, off_time, market_name, betfair_win_market_id, runner: Runner, sport888: Sport888PriceLeg, betfair: BetfairLayLeg, edge: float)`
  - `Horses888Output(computed_at, betfair_scraped_at, sport888_scraped_at, horse_count, horses: list[Horse888])`
  - `write_horses888_json(out, path)`

- [ ] **Step 1: Write the failing test** — `tests/test_horses888_models.py`:

```python
import json

from common.markettype import MarketType
from sport888_scraper.models import EachWayTerms
from arb_finder.models import (
    BetfairLayLeg,
    Horse888,
    Horses888Output,
    Runner,
    Sport888PriceLeg,
    write_horses888_json,
)


def _out() -> Horses888Output:
    return Horses888Output(
        computed_at="2026-07-22T12:01:00Z",
        betfair_scraped_at="2026-07-22T12:00:00Z",
        sport888_scraped_at="2026-07-22T12:00:30Z",
        horse_count=1,
        horses=[Horse888(
            venue="Worcester", country="GB",
            off_time="2026-07-22T13:55:00+01:00", market_name="12:55 Worcester",
            betfair_win_market_id="1.234",
            runner=Runner(name="Holy Legend", selection_id=99),
            sport888=Sport888PriceLeg(3.25, "9/4", EachWayTerms(0.2, 3)),
            betfair=BetfairLayLeg(win_lay=3.4, place_lay=1.5,
                                  place_market=MarketType.TOP_3),
            edge=0.05,
        )],
    )


def test_writes_camelcase_888_leg(tmp_path):
    p = tmp_path / "888horses.json"
    write_horses888_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["sport888ScrapedAt"] == "2026-07-22T12:00:30Z"
    h = data["horses"][0]
    assert h["betfairWinMarketId"] == "1.234"
    assert h["runner"]["selectionId"] == 99
    assert h["sport888"]["winPrice"] == 3.25
    assert h["sport888"]["winPriceRaw"] == "9/4"
    assert h["sport888"]["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    assert h["betfair"]["placeMarket"] == "TOP_3"
    # semantically correct: no "paddypower" key in the 888 output
    assert "paddypower" not in json.dumps(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_horses888_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'Horse888'`

- [ ] **Step 3: Modify `src/arb_finder/models.py`** — add these imports and definitions. Add the import near the top (after the existing `from paddypower_scraper.models import EachWayTerms`):

```python
from sport888_scraper.models import EachWayTerms as Sport888EachWayTerms
```

Then append at the end of the file:

```python
@dataclass(frozen=True)
class Sport888PriceLeg:
    win_price: float
    win_price_raw: str
    each_way_terms: Sport888EachWayTerms


@dataclass(frozen=True)
class Horse888:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: Runner
    sport888: Sport888PriceLeg
    betfair: BetfairLayLeg
    edge: float


@dataclass(frozen=True)
class Horses888Output:
    computed_at: str
    betfair_scraped_at: str
    sport888_scraped_at: str
    horse_count: int
    horses: list[Horse888]


HORSES888_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
    "sport888_scraped_at": "sport888ScrapedAt",
    "horse_count": "horseCount",
    "off_time": "offTime",
    "market_name": "marketName",
    "betfair_win_market_id": "betfairWinMarketId",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "each_way_terms": "eachWayTerms",
    "win_lay": "winLay",
    "place_lay": "placeLay",
    "place_market": "placeMarket",
}


def write_horses888_json(out: Horses888Output, path: Path | str) -> None:
    write_json(out, HORSES888_RENAME, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_horses888_models.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite to confirm no regression to horses.json**

Run: `uv run pytest tests/test_horses_models.py tests/test_horses_validation.py -q`
Expected: PASS (existing horses tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add src/arb_finder/models.py tests/test_horses888_models.py
git commit -m "feat(arb): Horse888 + 888horses.json serializer"
```

---

## Task 12: `find_horses_by_name` join

**Files:**
- Modify: `src/arb_finder/calculator.py`
- Test: `tests/test_find_horses_by_name.py`

**Interfaces:**
- Consumes: `each_way_arb_margin` (existing), `match_race`/`match_runner` (Task 10), `top_n_from_places`/`MarketType` (common.markettype), `betfair_scraper.models.ScrapeOutput`, `sport888_scraper.models.Sport888Output`, `Runner`/`BetfairLayLeg`/`Horse888`/`Sport888PriceLeg` (arb_finder.models).
- Produces:
  - `MatchStats(races_matched, races_unmatched, runners_priced, runners_unmatched)` (frozen dataclass)
  - `find_horses_by_name(betfair: ScrapeOutput, eight88: Sport888Output) -> tuple[list[Horse888], MatchStats]`

- [ ] **Step 1: Write the failing test** — `tests/test_find_horses_by_name.py`:

```python
from __future__ import annotations

from dataclasses import replace

import pytest

from common.markettype import MarketType
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from arb_finder.calculator import find_horses_by_name


def _betfair(win_lay=2.0, place_lay=1.4, venue="Worcester",
             off="2026-07-22T13:55:00+01:00", runner_name="Holy Legend") -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-07-22T12:00:00Z", race_count=1,
        races=[RaceOdds(
            race_id="1.1", venue=venue, country="GB", off_time=off,
            win_market_url="u", market_name="12:55 Worcester",
            market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z",
                               MarketType.TOP_3: "2026-07-22T12:00:00Z"},
            runners=[RunnerOdds(runner_name,
                                {MarketType.WIN: win_lay, MarketType.TOP_3: place_lay},
                                selection_id=99)])],
    )


def _eight88(runner_name="Holy Legend", venue="Worcester",
             off="2026-07-22T12:55:00+00:00", places=3) -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:30Z", race_count=1,
        races=[Sport888Race(
            venue=venue, country="uk-and-ireland", off_time=off,
            market_name="Winner Market", scraped_at="2026-07-22T12:00:30Z",
            each_way_terms=EachWayTerms(fraction=0.2, places=places),
            runners=[Sport888Runner(runner_name, 3.0, "2/1")])],
    )


def test_matched_runner_priced():
    horses, stats = find_horses_by_name(_betfair(2.0, 1.4), _eight88())
    assert len(horses) == 1
    h = horses[0]
    assert h.runner.selection_id == 99          # from matched Betfair runner
    assert h.runner.name == "Holy Legend"
    assert h.country == "GB"                     # from matched Betfair race
    assert h.betfair_win_market_id == "1.1"
    assert h.betfair.place_market is MarketType.TOP_3
    assert h.sport888.win_price == 3.0
    assert h.edge == pytest.approx(0.25)
    assert stats.races_matched == 1
    assert stats.runners_priced == 1


def test_race_not_in_betfair_counted_unmatched():
    horses, stats = find_horses_by_name(_betfair(off="2026-07-22T15:00:00+01:00"), _eight88())
    assert horses == []
    assert stats.races_unmatched == 1
    assert stats.races_matched == 0


def test_runner_name_mismatch_counted():
    horses, stats = find_horses_by_name(_betfair(), _eight88(runner_name="Ghost Horse"))
    assert horses == []
    assert stats.races_matched == 1
    assert stats.runners_unmatched == 1
    assert stats.runners_priced == 0


def test_venue_drift_still_matches():
    horses, _ = find_horses_by_name(_betfair(venue="Worcester (AW)"), _eight88(venue="Worcester"))
    assert len(horses) == 1


def test_null_each_way_skipped():
    e = _eight88()
    e.races[0] = replace(e.races[0], each_way_terms=None)
    horses, stats = find_horses_by_name(_betfair(), e)
    assert horses == []
    assert stats.races_matched == 1  # race matched, but unpriceable


def test_places_out_of_range_skipped():
    horses, _ = find_horses_by_name(_betfair(), _eight88(places=6))
    assert horses == []


def test_place_market_absent_skipped():
    bf = _betfair()
    bf.races[0] = replace(
        bf.races[0],
        market_scraped_at={MarketType.WIN: "2026-07-22T12:00:00Z"},
        runners=[RunnerOdds("Holy Legend", {MarketType.WIN: 2.0}, 99)])
    horses, _ = find_horses_by_name(bf, _eight88())
    assert horses == []


def test_zero_lay_skipped():
    assert find_horses_by_name(_betfair(0.0, 1.4), _eight88())[0] == []
    assert find_horses_by_name(_betfair(2.0, 0.0), _eight88())[0] == []


def test_null_win_price_skipped():
    e = _eight88()
    e.races[0] = replace(
        e.races[0],
        runners=[replace(e.races[0].runners[0], win_price=None, win_price_raw=None)])
    assert find_horses_by_name(_betfair(), e)[0] == []


def test_sorted_by_edge_desc():
    bf = ScrapeOutput(
        "2026-07-22T12:00:00Z", 1,
        [RaceOdds("1.1", "Worcester", "GB", "2026-07-22T13:55:00+01:00", "u",
                  "12:55 Worcester",
                  {MarketType.WIN: "2026-07-22T12:00:00Z",
                   MarketType.TOP_3: "2026-07-22T12:00:00Z"},
                  [RunnerOdds("A", {MarketType.WIN: 2.0, MarketType.TOP_3: 1.4}, 1),
                   RunnerOdds("B", {MarketType.WIN: 2.0, MarketType.TOP_3: 1.2}, 2)])])
    e = Sport888Output(
        "2026-07-22T12:00:30Z", 1,
        [Sport888Race("Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00",
                      "Winner Market", "2026-07-22T12:00:30Z", EachWayTerms(0.2, 3),
                      [Sport888Runner("A", 3.0, "2/1"), Sport888Runner("B", 3.0, "2/1")])])
    horses, _ = find_horses_by_name(bf, e)
    assert [h.edge for h in horses] == sorted([h.edge for h in horses], reverse=True)
    assert horses[0].runner.selection_id == 2  # B has higher edge (1.2 place lay)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_find_horses_by_name.py -q`
Expected: FAIL — `ImportError: cannot import name 'find_horses_by_name'`

- [ ] **Step 3: Modify `src/arb_finder/calculator.py`** — add imports at top (after existing imports):

```python
from dataclasses import dataclass

from betfair_scraper.models import RaceOdds, RunnerOdds
from sport888_scraper.models import Sport888Output
from .matching import match_race, match_runner
from .models import Horse888, Sport888PriceLeg
```

Then append at the end of the file:

```python
@dataclass(frozen=True)
class MatchStats:
    races_matched: int
    races_unmatched: int
    runners_priced: int
    runners_unmatched: int


def find_horses_by_name(
    betfair: ScrapeOutput, eight88: Sport888Output
) -> "tuple[list[Horse888], MatchStats]":
    """Every fully-priced 888 runner that matches a Betfair selection, with its
    each-way edge, sorted by edge descending. 888 carries no Betfair ids, so
    each race is matched by off-time+venue and each runner by normalized name.
    venue/country/off_time/ids come from the matched Betfair race/runner."""
    races_matched = races_unmatched = runners_priced = runners_unmatched = 0
    out: list[Horse888] = []

    for race888 in eight88.races:
        br = match_race(race888.off_time, race888.venue, betfair.races)
        if br is None:
            races_unmatched += 1
            continue
        races_matched += 1

        ew = race888.each_way_terms
        if ew is None:
            continue
        place_market = top_n_from_places(ew.places)
        if place_market is None or place_market not in br.market_scraped_at:
            continue

        for r888 in race888.runners:
            if r888.win_price is None or r888.win_price_raw is None:
                continue
            brun = match_runner(r888.name, br)
            if brun is None or brun.selection_id is None:
                runners_unmatched += 1
                continue
            win_lay = brun.lay.get(MarketType.WIN)
            place_lay = brun.lay.get(place_market)
            if (win_lay is None or place_lay is None
                    or win_lay <= 0.0 or place_lay <= 0.0):
                continue
            edge = each_way_arb_margin(
                p=r888.win_price, f=ew.fraction, bw=win_lay, bp=place_lay)
            runners_priced += 1
            out.append(Horse888(
                venue=br.venue,
                country=br.country,
                off_time=br.off_time,
                market_name=br.market_name,
                betfair_win_market_id=br.race_id,
                runner=Runner(name=r888.name, selection_id=brun.selection_id),
                sport888=Sport888PriceLeg(
                    win_price=r888.win_price, win_price_raw=r888.win_price_raw,
                    each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, place_lay=place_lay, place_market=place_market),
                edge=edge,
            ))

    out.sort(key=lambda h: h.edge, reverse=True)
    return out, MatchStats(races_matched, races_unmatched, runners_priced, runners_unmatched)
```

Note: `RaceOdds`/`RunnerOdds` are imported for type clarity/consistency with the module; they are used implicitly via the matcher's return types.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_find_horses_by_name.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Run the existing calculator tests (no regression)**

Run: `uv run pytest tests/test_calculator.py -q`
Expected: PASS (existing find_horses tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add src/arb_finder/calculator.py tests/test_find_horses_by_name.py
git commit -m "feat(arb): find_horses_by_name join (888 -> Betfair) + match stats"
```

---

## Task 13: `arb_finder --source 888` CLI mode

**Files:**
- Modify: `src/arb_finder/cli.py`
- Test: `tests/test_horses888_cli.py`

**Interfaces:**
- Consumes: `find_horses_by_name`/`MatchStats` (Task 12), `Sport888Output`/`validate_sport888_output` (Tasks 2/7), `Horses888Output`/`write_horses888_json` (Task 11), existing betfair validation.
- Produces: extended `arb_finder.cli.main` accepting `--source {paddypower,888}` (default `paddypower`). `--source 888` reads betfair + 888sport json, writes `888horses.json`, returns 0 (ok/empty), 1 (bad usage), 2 (input error). Default invocation unchanged.

- [ ] **Step 1: Write the failing test** — `tests/test_horses888_cli.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arb_finder import cli
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from betfair_scraper.models import write_betfair_json
from common.markettype import MarketType
from sport888_scraper.models import (
    EachWayTerms, Sport888Output, Sport888Race, Sport888Runner,
)
from sport888_scraper.output import write_sport888_json

NOW = datetime(2026, 7, 22, 12, 1, tzinfo=timezone.utc)


def _write_inputs(tmp_path: Path):
    bf = ScrapeOutput(
        "2026-07-22T12:00:00Z", 1,
        [RaceOdds("1.1", "Worcester", "GB", "2026-07-22T13:55:00+01:00", "u",
                  "12:55 Worcester",
                  {MarketType.WIN: "2026-07-22T12:00:00Z",
                   MarketType.TOP_3: "2026-07-22T12:00:00Z"},
                  [RunnerOdds("Holy Legend",
                              {MarketType.WIN: 2.0, MarketType.TOP_3: 1.4}, 99)])])
    e = Sport888Output(
        "2026-07-22T12:00:30Z", 1,
        [Sport888Race("Worcester", "uk-and-ireland", "2026-07-22T12:55:00+00:00",
                      "Winner Market", "2026-07-22T12:00:30Z", EachWayTerms(0.2, 3),
                      [Sport888Runner("Holy Legend", 3.0, "2/1")])])
    write_betfair_json(bf, tmp_path / "betfair.json")
    write_sport888_json(e, tmp_path / "888sport.json")


def test_source_888_writes_888horses(tmp_path: Path):
    _write_inputs(tmp_path)
    rc = cli.main(
        ["--source", "888",
         str(tmp_path / "betfair.json"),
         str(tmp_path / "888sport.json"),
         str(tmp_path / "888horses.json")],
        now=lambda: NOW)
    assert rc == 0
    data = json.loads((tmp_path / "888horses.json").read_text())
    assert data["horseCount"] == 1
    assert data["horses"][0]["sport888"]["winPrice"] == 3.0
    assert data["horses"][0]["betfairWinMarketId"] == "1.1"


def test_source_888_missing_input_exits_2(tmp_path: Path):
    rc = cli.main(
        ["--source", "888",
         str(tmp_path / "nope.json"),
         str(tmp_path / "also-nope.json"),
         str(tmp_path / "out.json")],
        now=lambda: NOW)
    assert rc == 2


def test_unknown_source_exits_1(tmp_path: Path):
    rc = cli.main(["--source", "ladbrokes"], now=lambda: NOW)
    assert rc == 1


def test_default_source_still_paddypower(tmp_path: Path, monkeypatch):
    # No --source, no args → existing paddypower path. Missing default inputs
    # → input error (exit 2), proving the default branch is taken unchanged.
    monkeypatch.chdir(tmp_path)
    rc = cli.main([], now=lambda: NOW)
    assert rc == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_horses888_cli.py -q`
Expected: FAIL — argument `--source` treated as a path / `AssertionError`

- [ ] **Step 3: Modify `src/arb_finder/cli.py`** — add imports after the existing imports:

```python
from sport888_scraper.models import Sport888Output
from sport888_scraper.validation import validate_sport888_output
from .calculator import find_horses_by_name
from .models import Horse888, Horses888Output, write_horses888_json
```

Replace the body of `main` so it dispatches on `--source` before the existing logic. The existing paddypower flow moves verbatim into `_run_paddypower`:

```python
def main(argv=None, *, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = "paddypower"
    if "--source" in argv:
        i = argv.index("--source")
        try:
            source = argv[i + 1]
        except IndexError:
            print("--source requires a value (paddypower|888)", file=sys.stderr)
            return 1
        del argv[i:i + 2]
    if source not in ("paddypower", "888"):
        print(f"unknown --source {source}; valid: paddypower, 888", file=sys.stderr)
        return 1
    if source == "888":
        return _run_888(argv, now)
    return _run_paddypower(argv, now)


def _run_paddypower(argv, now) -> int:
    # ---- existing main() body, unchanged ----
    try:
        betfair_in, paddy_in, out_path = parse_horses_cli_args(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    paddy_text = _read_or_none(paddy_in)
    if paddy_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    paddy_errors = validate_paddy_output(paddy_text)
    if paddy_errors:
        print(f"Error: {paddy_in} fails PaddyPower schema:", file=sys.stderr)
        for e in paddy_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    paddy = PaddyOutput.from_dict(json.loads(paddy_text))

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    horses = find_horses(betfair, paddy)
    output = HorsesOutput(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        paddypower_scraped_at=paddy.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_horses_json(output, out_path)
    print(f"Wrote {out_path} ({len(horses)} horses from {len(betfair.races)} BF races "
          f"and {len(paddy.races)} PP races)")
    return 0


def parse_888_cli_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", "888sport.json", "888horses.json")
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    raise ValueError(
        "usage: arb-finder --source 888                                    # defaults\n"
        "       arb-finder --source 888 <betfair-in> <888sport-in> <out>   # explicit"
    )


def _run_888(argv, now) -> int:
    try:
        betfair_in, eight88_in, out_path = parse_888_cli_args(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    eight88_text = _read_or_none(eight88_in)
    if eight88_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    eight88_errors = validate_sport888_output(eight88_text)
    if eight88_errors:
        print(f"Error: {eight88_in} fails 888sport schema:", file=sys.stderr)
        for e in eight88_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    eight88 = Sport888Output.from_dict(json.loads(eight88_text))

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    horses, stats = find_horses_by_name(betfair, eight88)
    output = Horses888Output(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        sport888_scraped_at=eight88.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_horses888_json(output, out_path)
    print(f"Wrote {out_path} ({len(horses)} horses; "
          f"races matched {stats.races_matched}/{stats.races_matched + stats.races_unmatched}, "
          f"runners unmatched {stats.runners_unmatched})")
    return 0
```

Note: keep the existing module-level imports (`ScrapeOutput`, `validate_scrape_output`, `PaddyOutput`, `validate_paddy_output`, `iso_utc`, `find_horses`, `HorsesOutput`, `write_horses_json`, `parse_horses_cli_args`, `_read_or_none`) — they are still used by `_run_paddypower`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_horses888_cli.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the existing arb CLI tests (no regression)**

Run: `uv run pytest tests/test_horses_cli.py -q`
Expected: PASS (existing paddypower CLI path unaffected)

- [ ] **Step 6: Commit**

```bash
git add src/arb_finder/cli.py tests/test_horses888_cli.py
git commit -m "feat(arb): --source 888 CLI mode -> 888horses.json"
```

---

## Task 14: Packaging + pipeline wiring

**Files:**
- Modify: `pyproject.toml`
- Modify: `run.sh`
- Modify: `.gitignore`
- Test: `tests/test_sport888_packaging.py`

**Interfaces:**
- Produces: `sport888_scraper` on the wheel package list + a `sport888-scraper` script entry; `run.sh` runs the 888 scrape + 888 arb after the PP pipeline; `888sport.json`/`888horses.json` git-ignored.

- [ ] **Step 1: Write the failing test** — `tests/test_sport888_packaging.py`:

```python
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_includes_sport888_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/sport888_scraper" in pkgs


def test_script_entry_present():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["sport888-scraper"] == "sport888_scraper.cli:main"


def test_run_sh_invokes_888_stages():
    text = (ROOT / "run.sh").read_text()
    assert "python -m sport888_scraper" in text
    assert "python -m arb_finder --source 888" in text


def test_gitignore_lists_888_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "888sport.json" in text
    assert "888horses.json" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sport888_packaging.py -q`
Expected: FAIL (4 failed)

- [ ] **Step 3: Modify `pyproject.toml`** — add the script entry under `[project.scripts]`:

```toml
sport888-scraper = "sport888_scraper.cli:main"
```

and add the package under `[tool.hatch.build.targets.wheel] packages`:

```toml
    "src/sport888_scraper",
```

- [ ] **Step 4: Modify `run.sh`** — replace the final `exec` line so the pipeline becomes:

```bash
uv run python -m betfair_scraper "$REGIONS"
uv run python -m paddypower_scraper "$REGIONS"
uv run python -m arb_finder
uv run python -m sport888_scraper "$REGIONS"
exec uv run python -m arb_finder --source 888
```

(Also update the header comment `# Pipeline: ...` to mention the 888 stages.)

- [ ] **Step 5: Modify `.gitignore`** — under `# Local scraper output`, add:

```
888sport.json
888horses.json
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_sport888_packaging.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml run.sh .gitignore tests/test_sport888_packaging.py
git commit -m "build(888): register package + wire 888 stages into run.sh"
```

---

## Task 15: Full-suite gate + opt-in live integration test

**Files:**
- Create: `tests/test_sport888_integration.py`

**Interfaces:**
- Consumes: real 888 API via `sport888_scraper.cli.main` with a real `BrowserSession`. Marked `integration`, opt-in via `RUN_INTEGRATION=1`.

- [ ] **Step 1: Run the entire unit suite (regression gate)**

Run: `uv run pytest -q`
Expected: PASS — all existing + new tests green, no failures.

- [ ] **Step 2: Write `tests/test_sport888_integration.py`**:

```python
"""Opt-in live test hitting the real 888sport API. Enable with RUN_INTEGRATION=1.
Skipped by default so CI/unit runs need no network or browser."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

if not os.environ.get("RUN_INTEGRATION"):
    pytest.skip("integration test; set RUN_INTEGRATION=1 to run",
                allow_module_level=True)


def test_live_scrape_writes_valid_json(tmp_path: Path):
    from sport888_scraper import cli
    from sport888_scraper.validation import validate_sport888_output

    out = tmp_path / "888sport.json"
    rc = cli.main(["gb-ie"], out_path=out)
    assert rc == 0, "live 888 scrape should succeed"
    text = out.read_text()
    assert validate_sport888_output(text) == []
    data = json.loads(text)
    assert data["raceCount"] == len(data["races"])
```

- [ ] **Step 3: Run the integration test locally (manual, optional)**

Run: `RUN_INTEGRATION=1 uv run pytest tests/test_sport888_integration.py -q`
Expected: PASS when GB/IE races are live and the network/browser is available. (Skipped without the env var.)

- [ ] **Step 4: Confirm default run still skips it**

Run: `uv run pytest tests/test_sport888_integration.py -q`
Expected: `1 skipped`

- [ ] **Step 5: Commit**

```bash
git add tests/test_sport888_integration.py
git commit -m "test(888): opt-in live integration test"
```

---

## Self-Review

**Spec coverage:**
- Full-day `getSchedule` index → Task 4 (parser) + Task 9 (CLI fetch). ✓
- Per-race `getRacecard` with EW terms + winner-market runners → Task 5. ✓
- Region slugs `uk-and-ireland`/`north-america` → Task 1 + Task 9 filtering. ✓
- Cookie warmup, no `x-forwarded-for` → Task 8 (warmup to 888 page, `credentials: 'include'`). ✓
- Name+time join, exact-match-only, skip+count → Task 10 + Task 12. ✓
- `888sport.json` = complete card (no Betfair filtering; unmatched runners visible) → Task 5/6/9 emit every winner-market runner; join filtering only in Task 12. ✓
- `888horses.json` = priced arbs only, matched Betfair venue/country/ids, 888-named leg → Task 11 + Task 12. ✓
- PP path / web page / publish.sh untouched → no task modifies them; Tasks 11/12/13 are additive; regression gates in Tasks 11/12/13/15. ✓
- Pipeline wiring, packaging, gitignore → Task 14. ✓
- `allow_each_way != "1"` → no EW terms → Task 5 (`_parse_eachway`) + Task 12 skip. ✓
- Error handling (index fail=1, per-race skip+count, empty day=0, all-fail=1, arb input error=2) → Task 9 + Task 13. ✓
- Opt-in integration test → Task 15. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `Sport888Output`/`Sport888Race`/`Sport888Runner`/`EachWayTerms` defined in Task 2 and used identically in Tasks 5/6/7/9/12/13. `Horse888`/`Sport888PriceLeg`/`Horses888Output`/`write_horses888_json` defined in Task 11, used in Tasks 12/13. `find_horses_by_name` returns `tuple[list[Horse888], MatchStats]` in Task 12 and is consumed that way in Task 13. `match_race`/`match_runner` signatures in Task 10 match their calls in Task 12. `slugs_for_all` (Task 1) consumed in Task 9. ✓
