# Python Rewrite — Plan 1: Foundation (scaffold + `common` + PaddyPower fold-in)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the single consolidated Python project at the repo root, build the shared `common` package (regions, market type, ISO validation, time helpers, JSON serializer), and relocate the existing PaddyPower scraper into it — including a brand-new Python schema validator — leaving the PaddyPower test suite green.

**Architecture:** A `src/`-layout uv project at the repo root holds four packages: `common`, `paddypower_scraper`, `betfair_scraper` (Plan 2), `arb_finder` (Plan 3). This plan builds `common` and folds `paddypower_scraper` in. The Kotlin tree stays untouched until Plan 3's cutover, so it remains available as a behavioral reference during porting.

**Tech Stack:** Python ≥3.11, uv, pytest, Playwright (PaddyPower only), stdlib `json`/`urllib`/`zoneinfo`.

**Spec:** `docs/superpowers/specs/2026-05-26-python-rewrite-design.md`

**Reference (do not delete yet):** Kotlin sources under `src/main/kotlin/com/horsey/scraper/` are the behavioral oracle for `common` (`Regions.kt`, `MarketClassifier.kt`, `SchemaValidator.kt` ISO helpers) and the PaddyPower validator (`paddypower/PaddySchemaValidator.kt`).

---

## Task 1: Scaffold the consolidated project

**Files:**
- Create: `pyproject.toml`
- Create: `src/common/__init__.py`
- Create: `src/betfair_scraper/__init__.py`
- Create: `src/arb_finder/__init__.py`

> Note: `src/paddypower_scraper/` is created by the move in Task 7, not here.

- [ ] **Step 1: Verify uv is installed**

Run: `uv --version`
Expected: prints a version (e.g. `uv 0.4.x`). If missing: `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 2: Create `pyproject.toml` at the repo root**

```toml
[project]
name = "horsey-scraper"
version = "1.0.0"
description = "Horse-racing lay-price scraper + each-way arb finder (Betfair + PaddyPower)"
requires-python = ">=3.11"
dependencies = ["playwright>=1.42"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
betfair-scraper = "betfair_scraper.cli:main"
paddypower-scraper = "paddypower_scraper.cli:main"
arb-finder = "arb_finder.cli:main"

# NOTE: src/paddypower_scraper is added to this list in Task 7, after the
# move creates the directory. Listing a non-existent package dir here would
# make `uv sync` fail.
[tool.hatch.build.targets.wheel]
packages = [
    "src/common",
    "src/betfair_scraper",
    "src/arb_finder",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = [
    "integration: live network/browser test, opt-in via RUN_INTEGRATION=1",
]
```

> `pythonpath = ["src"]` lets pytest import the packages without an editable install step during early tasks. The console-script entry points still require the build backend to see all four packages, which is why `paddypower_scraper` is listed now even though it arrives in Task 7.

- [ ] **Step 3: Create package `__init__.py` files**

`src/common/__init__.py`:
```python
"""Shared helpers used by every scraper: regions, market types, ISO
validation, time conversion, and JSON serialization."""
```

`src/betfair_scraper/__init__.py`:
```python
"""Betfair Exchange API scraper. Populated in Plan 2."""
```

`src/arb_finder/__init__.py`:
```python
"""Each-way arbitrage finder. Populated in Plan 3."""
```

- [ ] **Step 4: Create `tests/__init__.py` is NOT needed — verify tests dir**

Run: `mkdir -p tests && ls -d tests`
Expected: `tests` exists. (pytest discovers `tests/` via `testpaths`; no `__init__.py` required at the tests root.)

- [ ] **Step 5: Sync the environment**

Run: `uv sync`
Expected: creates `.venv/`, installs `playwright` + `pytest`, writes `uv.lock`. (Chromium browser binary install is deferred to Plan 2/whenever PP runs live; not needed for unit tests.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/common/__init__.py src/betfair_scraper/__init__.py src/arb_finder/__init__.py
git commit -m "Scaffold consolidated Python project (pyproject + src packages)"
```

---

## Task 2: `common/regions.py` — region ids + country codes (TDD)

Behavioral oracle: `src/main/kotlin/com/horsey/scraper/Regions.kt` (`countriesForAll`) and `Main.kt::parseRegions`. **Decision (see spec):** `parse_regions` returns region **ids** (`{"gb-ie"}`), `countries_for_all` maps ids → country codes (`{"GB","IE"}`).

**Files:**
- Create: `src/common/regions.py`
- Test: `tests/test_regions.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_regions.py`:
```python
"""Tests for common.regions: parse region ids and map them to countries."""

from __future__ import annotations

import pytest

from common.regions import REGION_COUNTRIES, countries_for_all, parse_regions


class TestParseRegions:
    def test_single_gb_ie(self):
        assert parse_regions("gb-ie") == frozenset({"gb-ie"})

    def test_single_us(self):
        assert parse_regions("us") == frozenset({"us"})

    def test_combo(self):
        assert parse_regions("gb-ie,us") == frozenset({"gb-ie", "us"})

    def test_case_insensitive_and_whitespace(self):
        assert parse_regions(" GB-IE ,  US ") == frozenset({"gb-ie", "us"})

    def test_dedupes(self):
        assert parse_regions("us,us") == frozenset({"us"})

    def test_unknown_region_raises_with_valid_list(self):
        with pytest.raises(ValueError, match="valid: gb-ie,us"):
            parse_regions("xx")

    def test_unknown_region_names_offender(self):
        with pytest.raises(ValueError, match="xx"):
            parse_regions("gb-ie,xx")

    def test_empty_arg_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("   ")

    def test_commas_only_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions(",, ,")


class TestCountriesForAll:
    def test_gb_ie(self):
        assert countries_for_all(frozenset({"gb-ie"})) == frozenset({"GB", "IE"})

    def test_us(self):
        assert countries_for_all(frozenset({"us"})) == frozenset({"US"})

    def test_union(self):
        assert countries_for_all(frozenset({"gb-ie", "us"})) == frozenset(
            {"GB", "IE", "US"}
        )


class TestRegionTable:
    def test_table(self):
        assert REGION_COUNTRIES == {
            "gb-ie": frozenset({"GB", "IE"}),
            "us": frozenset({"US"}),
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_regions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.regions'`.

- [ ] **Step 3: Implement `common/regions.py`**

```python
"""Region ids ↔ Betfair country codes. Pure, no I/O.

Region ids are stable lowercase CLI tokens (`gb-ie`, `us`). Country
codes follow Betfair's `event.countryCode` (`GB`, `IE`, `US`)."""

from __future__ import annotations

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IE"}),
    "us": frozenset({"US"}),
}

_VALID = ",".join(sorted(REGION_COUNTRIES))


def parse_regions(arg: str) -> frozenset[str]:
    """Parse a comma-separated region string into a set of region ids.

    Case-insensitive, whitespace-tolerant. Raises ValueError on an empty
    result or any unknown id (message lists the offenders and the valid set)."""
    ids = frozenset(
        part.strip().lower() for part in arg.split(",") if part.strip()
    )
    if not ids:
        raise ValueError(f"regions must be non-empty; valid: {_VALID}")
    unknown = sorted(ids - REGION_COUNTRIES.keys())
    if unknown:
        raise ValueError(
            f"unknown region(s) {','.join(unknown)}; valid: {_VALID}"
        )
    return ids


def countries_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of country codes for every region id. Assumes ids are valid
    (caller validates first via parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_COUNTRIES[rid]
    return frozenset(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_regions.py -q`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add src/common/regions.py tests/test_regions.py
git commit -m "common.regions: parse region ids + map to country codes"
```

---

## Task 3: `common/markettype.py` — MarketType enum (TDD)

Behavioral oracle: `Models.kt::MarketType` and `ArbCalculator.kt::topNFromPlaces`.

**Files:**
- Create: `src/common/markettype.py`
- Test: `tests/test_markettype.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_markettype.py`:
```python
"""Tests for common.markettype."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places


def test_member_names_and_values_match():
    assert [m.name for m in MarketType] == ["WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"]
    assert all(m.value == m.name for m in MarketType)


def test_declaration_order_is_win_first():
    # Output key order depends on this; WIN must come first.
    assert list(MarketType)[0] is MarketType.WIN


def test_top_n_from_places():
    assert top_n_from_places(2) is MarketType.TOP_2
    assert top_n_from_places(3) is MarketType.TOP_3
    assert top_n_from_places(4) is MarketType.TOP_4
    assert top_n_from_places(5) is MarketType.TOP_5


def test_top_n_from_places_out_of_range():
    assert top_n_from_places(1) is None
    assert top_n_from_places(6) is None
    assert top_n_from_places(0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_markettype.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.markettype'`.

- [ ] **Step 3: Implement `common/markettype.py`**

```python
"""The five lay markets we track. Enum member order defines JSON key order
(WIN first), so do not reorder."""

from __future__ import annotations

import enum


class MarketType(enum.Enum):
    WIN = "WIN"
    TOP_2 = "TOP_2"
    TOP_3 = "TOP_3"
    TOP_4 = "TOP_4"
    TOP_5 = "TOP_5"


def top_n_from_places(n: int) -> "MarketType | None":
    """Map a place count (2..5) to its TOP_N market; None outside 2..5."""
    return {
        2: MarketType.TOP_2,
        3: MarketType.TOP_3,
        4: MarketType.TOP_4,
        5: MarketType.TOP_5,
    }.get(n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_markettype.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/common/markettype.py tests/test_markettype.py
git commit -m "common.markettype: MarketType enum + top_n_from_places"
```

---

## Task 4: `common/isovalid.py` — ISO-8601 validators (TDD)

Behavioral oracle: the `isIsoUtc` / `isIsoOffsetDateTime` helpers duplicated in `SchemaValidator.kt`, `ArbSchemaValidator.kt`, `PaddySchemaValidator.kt`.

**Files:**
- Create: `src/common/isovalid.py`
- Test: `tests/test_isovalid.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_isovalid.py`:
```python
"""Tests for common.isovalid."""

from __future__ import annotations

from common.isovalid import is_iso_offset_datetime, is_iso_utc


class TestIsIsoUtc:
    def test_z_instant(self):
        assert is_iso_utc("2026-05-25T17:05:56.890289Z")

    def test_z_whole_second(self):
        assert is_iso_utc("2026-05-25T17:05:56Z")

    def test_offset_form_is_not_utc_instant(self):
        # An offset like +01:00 is a valid moment but not the 'Z' instant form.
        assert not is_iso_utc("2026-05-25T18:05:00+01:00")

    def test_garbage(self):
        assert not is_iso_utc("not-a-date")

    def test_empty(self):
        assert not is_iso_utc("")


class TestIsIsoOffsetDateTime:
    def test_bst_offset(self):
        assert is_iso_offset_datetime("2026-05-25T18:05:00+01:00")

    def test_z_offset(self):
        assert is_iso_offset_datetime("2026-01-15T13:30:00Z")

    def test_missing_offset(self):
        assert not is_iso_offset_datetime("2026-05-25T18:05:00")

    def test_garbage(self):
        assert not is_iso_offset_datetime("nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_isovalid.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `common/isovalid.py`**

```python
"""ISO-8601 validation helpers shared by the schema validators.

`is_iso_utc`  — the 'Z' UTC-instant form (java.time.Instant.parse equiv).
`is_iso_offset_datetime` — any date-time carrying an explicit offset
                           (ISO_OFFSET_DATE_TIME equiv), 'Z' or +hh:mm."""

from __future__ import annotations

from datetime import datetime


def is_iso_utc(v: str) -> bool:
    """True iff `v` is an ISO-8601 instant in the trailing-'Z' UTC form."""
    if not v.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def is_iso_offset_datetime(v: str) -> bool:
    """True iff `v` is an ISO-8601 date-time with an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_isovalid.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/common/isovalid.py tests/test_isovalid.py
git commit -m "common.isovalid: ISO-8601 UTC + offset validators"
```

---

## Task 5: `common/timeutil.py` — UTC→London + UTC instant formatting (TDD)

Behavioral oracle: `BetfairResponses.kt::utcToLondon`, PaddyPower `races.py::_utc_to_london`, PaddyPower `cli.py::_iso_utc`.

**Files:**
- Create: `src/common/timeutil.py`
- Test: `tests/test_timeutil.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_timeutil.py`:
```python
"""Tests for common.timeutil."""

from __future__ import annotations

from datetime import datetime, timezone

from common.timeutil import iso_utc, utc_to_london


class TestUtcToLondon:
    def test_bst_summer(self):
        # 17:05 UTC in May (BST, +01:00) → 18:05 local.
        assert utc_to_london("2026-05-25T17:05:00Z") == "2026-05-25T18:05:00+01:00"

    def test_gmt_winter(self):
        # 13:30 UTC in January (GMT, +00:00).
        assert utc_to_london("2026-01-15T13:30:00Z") == "2026-01-15T13:30:00Z"

    def test_accepts_offset_input(self):
        assert utc_to_london("2026-05-25T17:05:00+00:00") == "2026-05-25T18:05:00+01:00"

    def test_garbage_returns_none(self):
        assert utc_to_london("not-a-date") is None


class TestIsoUtc:
    def test_formats_z(self):
        dt = datetime(2026, 5, 25, 17, 5, 56, 890289, tzinfo=timezone.utc)
        assert iso_utc(dt) == "2026-05-25T17:05:56.890289Z"

    def test_converts_aware_to_utc(self):
        from zoneinfo import ZoneInfo

        dt = datetime(2026, 5, 25, 18, 5, 0, tzinfo=ZoneInfo("Europe/London"))
        assert iso_utc(dt) == "2026-05-25T17:05:00Z"
```

> Note: GMT-winter renders as `...Z` because Python emits `+00:00`, which we normalize to `Z` for the UTC-offset case. The Kotlin side rendered `Z` here too (`ISO_OFFSET_DATE_TIME` of a UTC instant). BST renders `+01:00`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_timeutil.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `common/timeutil.py`**

```python
"""Time helpers: UTC→Europe/London ISO-offset strings, and UTC-instant
formatting. Pure, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def utc_to_london(iso_utc_str: str) -> "str | None":
    """Convert an ISO-8601 UTC string to a Europe/London ISO-offset string.

    Returns None on unparseable input. A UTC instant renders with a 'Z'
    suffix when London is on GMT (+00:00) and '+01:00' when on BST,
    matching the Kotlin ISO_OFFSET_DATE_TIME output."""
    try:
        parsed = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    london = parsed.astimezone(LONDON)
    return london.isoformat().replace("+00:00", "Z")


def iso_utc(dt: datetime) -> str:
    """Format an aware datetime as an ISO-8601 UTC instant ('...Z')."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_timeutil.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/common/timeutil.py tests/test_timeutil.py
git commit -m "common.timeutil: utc_to_london + iso_utc"
```

---

## Task 6: `common/jsonio.py` — dataclass → camelCase JSON serializer (TDD)

Generalizes PaddyPower's `output.py`. Handles frozen dataclasses, lists, dicts (including `MarketType`-keyed dicts → `.name`), `MarketType` values → `.name`, and `None` → `null`. Field renaming via a caller-supplied snake→camel map. Writes atomically.

**Files:**
- Create: `src/common/jsonio.py`
- Test: `tests/test_jsonio.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_jsonio.py`:
```python
"""Tests for common.jsonio: dataclass tree → camelCase dict → atomic JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from common.jsonio import to_camel_dict, write_json
from common.markettype import MarketType


@dataclass(frozen=True)
class Leaf:
    win_price: float | None
    selection_id: int | None


@dataclass(frozen=True)
class Node:
    market_name: str
    lay: dict
    children: list = field(default_factory=list)


RENAME = {
    "win_price": "winPrice",
    "selection_id": "selectionId",
    "market_name": "marketName",
}


class TestToCamelDict:
    def test_renames_fields(self):
        out = to_camel_dict(Leaf(win_price=2.5, selection_id=66986352), RENAME)
        assert out == {"winPrice": 2.5, "selectionId": 66986352}

    def test_none_preserved(self):
        out = to_camel_dict(Leaf(win_price=None, selection_id=None), RENAME)
        assert out == {"winPrice": None, "selectionId": None}

    def test_int_stays_int(self):
        out = to_camel_dict(Leaf(win_price=5.0, selection_id=832048), RENAME)
        assert isinstance(out["selectionId"], int)
        assert isinstance(out["winPrice"], float)

    def test_markettype_dict_keys_become_names(self):
        node = Node(
            market_name="x",
            lay={MarketType.WIN: 2.72, MarketType.TOP_2: 1.99},
        )
        out = to_camel_dict(node, RENAME)
        assert out["lay"] == {"WIN": 2.72, "TOP_2": 1.99}

    def test_markettype_value_becomes_name(self):
        @dataclass(frozen=True)
        class Holder:
            t: MarketType

        assert to_camel_dict(Holder(MarketType.TOP_4), {}) == {"t": "TOP_4"}

    def test_nested_dataclasses_and_lists(self):
        node = Node(
            market_name="race",
            lay={MarketType.WIN: None},
            children=[Leaf(1.0, 2), Leaf(None, None)],
        )
        out = to_camel_dict(node, RENAME)
        assert out["children"] == [
            {"winPrice": 1.0, "selectionId": 2},
            {"winPrice": None, "selectionId": None},
        ]

    def test_field_order_preserved(self):
        out = to_camel_dict(Node("n", {}, []), RENAME)
        assert list(out.keys()) == ["marketName", "lay", "children"]


class TestWriteJson:
    def test_writes_and_reads_back(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert json.loads(target.read_text()) == {"winPrice": 2.5, "selectionId": 7}

    def test_atomic_no_tmp_left(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert not (tmp_path / "out.json.tmp").exists()

    def test_two_space_indent(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert '\n  "winPrice"' in target.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jsonio.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `common/jsonio.py`**

```python
"""Serialize a frozen-dataclass tree to JSON with camelCase keys.

Generalizes the PaddyPower output writer. The caller supplies a
snake→camel field-name map (each package owns its own). Enum values and
enum dict-keys are emitted as their `.name`. Written atomically."""

from __future__ import annotations

import enum
import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping


def _key(k: Any) -> Any:
    return k.name if isinstance(k, enum.Enum) else k


def to_camel_dict(obj: Any, rename: Mapping[str, str]) -> Any:
    """Recursively convert `obj` into JSON-ready primitives.

    - dataclass → dict with field names renamed via `rename` (unmapped
      names pass through unchanged), declaration order preserved.
    - Enum → its `.name`.
    - dict → dict with Enum keys converted to `.name`, values recursed.
    - list/tuple → list of recursed elements.
    - everything else (str/int/float/bool/None) → unchanged."""
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in fields(obj):
            out[rename.get(f.name, f.name)] = to_camel_dict(getattr(obj, f.name), rename)
        return out
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, dict):
        return {_key(k): to_camel_dict(v, rename) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_camel_dict(x, rename) for x in obj]
    return obj


def write_json(obj: Any, rename: Mapping[str, str], path: Path | str) -> None:
    """Serialize `obj` to `path` as 2-space-indented JSON, atomically
    (write to `{path}.tmp`, then os.replace)."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = to_camel_dict(obj, rename)
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jsonio.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/common/jsonio.py tests/test_jsonio.py
git commit -m "common.jsonio: dataclass→camelCase atomic JSON serializer"
```

---

## Task 7: Move PaddyPower into `src/`, repoint to `common`

This relocates the existing `paddypower-py/` package and tests, then rewires region/time usage to `common`. The PaddyPower scraping/parsing logic itself is unchanged.

**Files:**
- Move: `paddypower-py/src/paddypower_scraper/*` → `src/paddypower_scraper/*`
- Move: `paddypower-py/tests/*` → `tests/*` (merge into the existing `tests/`)
- Modify: `src/paddypower_scraper/filtering.py`
- Modify: `src/paddypower_scraper/races.py`
- Modify: `src/paddypower_scraper/cli.py`
- Modify: `tests/test_filtering.py`
- Delete: `paddypower-py/` (after move)

- [ ] **Step 1: Move source and tests with git**

```bash
git mv paddypower-py/src/paddypower_scraper src/paddypower_scraper
git mv paddypower-py/tests/conftest.py tests/conftest.py
git mv paddypower-py/tests/fixtures tests/fixtures
for f in test_api test_browser_smoke test_cli test_filtering test_meetings test_output test_races; do
  git mv "paddypower-py/tests/$f.py" "tests/$f.py"
done
git mv paddypower-py/README.md docs/paddypower-scraper.md
git rm paddypower-py/tests/__init__.py paddypower-py/pyproject.toml paddypower-py/uv.lock
rm -rf paddypower-py   # remove any leftover untracked dirs (.venv, __pycache__)
```

> The PaddyPower README content is preserved at `docs/paddypower-scraper.md`; the root README is rewritten in Plan 3. `tests/__init__.py` from PaddyPower is removed because the consolidated `tests/` is discovered via `testpaths`, not as a package.

- [ ] **Step 2: Repoint `filtering.py` to `common`**

Replace `src/paddypower_scraper/filtering.py` with (drops the local `REGION_COUNTRIES`/`parse_regions`, keeps the PP-specific window + in_window, re-exports for any importer):

```python
"""London-day windowing and in-window check for already-fetched races.
Region parsing now lives in common.regions; re-exported for convenience."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from common.regions import REGION_COUNTRIES, countries_for_all, parse_regions

__all__ = [
    "REGION_COUNTRIES",
    "countries_for_all",
    "parse_regions",
    "london_day_window",
    "in_window",
    "LONDON",
]

LONDON = ZoneInfo("Europe/London")


def london_day_window(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return (now_utc, end_of_today_london_in_utc).

    `end` is midnight of *tomorrow* Europe/London converted to UTC
    (exclusive). A race at 23:59 London passes; 00:00 next-day does not."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    now_london = now_utc.astimezone(LONDON)
    tomorrow_london = (now_london + timedelta(days=1)).date()
    end_london = datetime.combine(tomorrow_london, time(0, 0), tzinfo=LONDON)
    return (now_utc, end_london.astimezone(timezone.utc))


def in_window(start_time_utc: str, window: tuple[datetime, datetime]) -> bool:
    """`start_time_utc` is an ISO-8601 UTC string. True iff
    window[0] <= parsed < window[1]."""
    parsed = datetime.fromisoformat(start_time_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return window[0] <= parsed < window[1]
```

- [ ] **Step 3: Update `cli.py` to derive countries from region ids**

In `src/paddypower_scraper/cli.py`, the import line `from .filtering import in_window, london_day_window, parse_regions` becomes:

```python
from .filtering import in_window, london_day_window
from common.regions import countries_for_all, parse_regions
```

And replace the region-parse block:

```python
    try:
        countries = parse_regions(region_arg)
    except ValueError as e:
```

with:

```python
    try:
        countries = countries_for_all(parse_regions(region_arg))
    except ValueError as e:
```

(Leaves the rest of `cli.py` — `s.country_code in countries` filtering — unchanged, since `countries` is still a frozenset of country codes.)

- [ ] **Step 4: Repoint `races.py`'s UTC→London helper to `common`**

In `src/paddypower_scraper/races.py`, find the local `_utc_to_london` definition and its call sites. Replace the local function with an import-and-alias at the top:

```python
from common.timeutil import utc_to_london as _utc_to_london
```

Delete the local `def _utc_to_london(...)` body. (If the local implementation differs in edge behavior, keep the call sites identical — `common.timeutil.utc_to_london` returns the same ISO-offset string or `None`.)

Run after editing: `uv run pytest tests/test_races.py -q` — Expected: PASS (confirms the shared helper matches).

- [ ] **Step 5: Update `tests/test_filtering.py` for the new region contract**

`parse_regions` now returns region **ids**; country mapping moves to `countries_for_all`. Replace `tests/test_filtering.py`'s imports and `TestParseRegions`/`TestRegionCountries` classes:

```python
from paddypower_scraper.filtering import in_window, london_day_window
from common.regions import (
    REGION_COUNTRIES,
    countries_for_all,
    parse_regions,
)
```

```python
class TestParseRegions:
    def test_single_gb_ie(self):
        assert parse_regions("gb-ie") == frozenset({"gb-ie"})

    def test_combo_to_countries(self):
        assert countries_for_all(parse_regions("gb-ie,us")) == frozenset(
            {"GB", "IE", "US"}
        )

    def test_unknown_region_raises(self):
        with pytest.raises(ValueError, match="valid: gb-ie,us"):
            parse_regions("xx")

    def test_empty_arg_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_regions("")
```

```python
class TestRegionCountries:
    def test_table(self):
        assert REGION_COUNTRIES == {
            "gb-ie": frozenset({"GB", "IE"}),
            "us": frozenset({"US"}),
        }
```

(Keep the `TestLondonDayWindow` and `TestInWindow` classes exactly as they were.)

- [ ] **Step 6: Update stale "see Kotlin" comments**

In `tests/test_api.py` (line ~76) and `tests/test_filtering.py`, replace comments referencing "Kotlin PaddyClient" / "Kotlin Regions.kt" with "see common.regions" / "see api.py". (Search: `grep -rn "Kotlin" tests/`.)

- [ ] **Step 6b: Register `paddypower_scraper` in the wheel packages + re-sync**

The directory now exists, so add it to `pyproject.toml`'s
`[tool.hatch.build.targets.wheel]` packages list (and drop the NOTE comment):

```toml
[tool.hatch.build.targets.wheel]
packages = [
    "src/common",
    "src/betfair_scraper",
    "src/paddypower_scraper",
    "src/arb_finder",
]
```

Run: `uv sync`
Expected: succeeds (re-resolves with all four packages present).

- [ ] **Step 7: Run the full PaddyPower suite (minus the contract test, fixed in Task 10)**

Run: `uv run pytest tests/test_api.py tests/test_meetings.py tests/test_races.py tests/test_filtering.py tests/test_cli.py -q`
Expected: PASS. (`test_output.py` still has the Kotlin contract test — addressed in Task 10. `test_browser_smoke.py` is opt-in/skipped.)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "Move paddypower_scraper into src/, repoint regions+time to common"
```

---

## Task 8: `paddypower_scraper/validation.py` — Python schema validator (TDD)

**New code.** Port `src/main/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidator.kt` (`validatePaddyOutput`) to Python. The arb finder (Plan 3) and the recolored contract test (Task 10) both depend on it. Behavioral oracle and test cases: `PaddySchemaValidator.kt` + `src/test/kotlin/com/horsey/scraper/paddypower/PaddySchemaValidatorTest.kt`.

**Files:**
- Create: `src/paddypower_scraper/validation.py`
- Test: `tests/test_paddy_validation.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_paddy_validation.py`:
```python
"""Tests for the PaddyPower schema validator (port of PaddySchemaValidator.kt)."""

from __future__ import annotations

import json

from paddypower_scraper.validation import validate_paddy_output


def _valid() -> dict:
    return {
        "scrapedAt": "2026-05-25T17:05:58.384555Z",
        "raceCount": 1,
        "races": [
            {
                "venue": "Ballinrobe",
                "country": "IE",
                "offTime": "2026-05-25T18:05:00+01:00",
                "marketName": "18:05 Ballinrobe",
                "raceUrl": "https://www.paddypower.com/...",
                "scrapedAt": "2026-05-25T17:05:58.384555Z",
                "betfairWinMarketId": "1.258528220",
                "eachWayTerms": {"fraction": 0.2, "places": 3},
                "runners": [
                    {"name": "Sony Bill", "selectionId": 66986352,
                     "winPrice": 2.72, "winPriceRaw": "7/4"},
                    {"name": "Spare", "selectionId": None,
                     "winPrice": None, "winPriceRaw": None},
                ],
            }
        ],
    }


def _v(payload: dict) -> list[str]:
    return validate_paddy_output(json.dumps(payload))


class TestValid:
    def test_clean_payload(self):
        assert _v(_valid()) == []

    def test_null_eachway_ok(self):
        p = _valid()
        p["races"][0]["eachWayTerms"] = None
        assert _v(p) == []


class TestTopLevel:
    def test_not_json(self):
        errs = validate_paddy_output("{not json")
        assert errs and "not valid JSON" in errs[0]

    def test_missing_scraped_at(self):
        p = _valid(); del p["scrapedAt"]
        assert any("scrapedAt" in e for e in _v(p))

    def test_bad_scraped_at(self):
        p = _valid(); p["scrapedAt"] = "2026-05-25T18:05:00+01:00"
        assert any("scrapedAt is not ISO-8601 UTC" in e for e in _v(p))

    def test_race_count_mismatch(self):
        p = _valid(); p["raceCount"] = 5
        assert any("raceCount" in e for e in _v(p))


class TestRace:
    def test_bad_offtime(self):
        p = _valid(); p["races"][0]["offTime"] = "2026-05-25T18:05:00"
        assert any("offTime not ISO-8601 with offset" in e for e in _v(p))

    def test_bad_race_scraped_at(self):
        p = _valid(); p["races"][0]["scrapedAt"] = "nope"
        assert any("scrapedAt not ISO-8601 UTC" in e for e in _v(p))

    def test_eachway_fraction_out_of_range(self):
        p = _valid(); p["races"][0]["eachWayTerms"]["fraction"] = 0
        assert any("fraction must be in (0,1]" in e for e in _v(p))

    def test_eachway_places_out_of_range(self):
        p = _valid(); p["races"][0]["eachWayTerms"]["places"] = 7
        assert any("places must be in" in e for e in _v(p))


class TestRunner:
    def test_price_parity_violation(self):
        p = _valid()
        p["races"][0]["runners"][0]["winPriceRaw"] = None  # price set, raw null
        assert any("price parity violation" in e for e in _v(p))

    def test_win_price_not_number(self):
        p = _valid(); p["races"][0]["runners"][0]["winPrice"] = "2.72"
        assert any("winPrice" in e for e in _v(p))

    def test_missing_name(self):
        p = _valid(); del p["races"][0]["runners"][0]["name"]
        assert any("name" in e for e in _v(p))
```

> Cross-check these branches against `PaddySchemaValidatorTest.kt` and add any case it covers that is missing here (e.g. places range is **1..6** for PaddyPower, unlike the arb validator's 2..5).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_paddy_validation.py -q`
Expected: FAIL — `ModuleNotFoundError: paddypower_scraper.validation`.

- [ ] **Step 3: Implement `src/paddypower_scraper/validation.py`**

```python
"""Validate a paddypower.json payload string against the schema.

Port of PaddySchemaValidator.kt. Returns [] when valid, else a list of
human-readable error strings (one per violation)."""

from __future__ import annotations

import json
from typing import Any

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(1, 7)  # 1..6 inclusive (PaddyPower side)


def validate_paddy_output(text: str) -> list[str]:
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
        _require_str(race, "raceUrl", errors)
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
            wp_null = wp is None
            raw_null = raw is None
            if wp_null != raw_null:
                errors.append(
                    f"{rctx}: price parity violation — winPrice null={wp_null}, "
                    f"winPriceRaw null={raw_null}"
                )
            if not wp_null and (not isinstance(wp, (int, float)) or isinstance(wp, bool)):
                errors.append(f"{rctx}.winPrice: not a number")
            if not raw_null and not isinstance(raw, str):
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_paddy_validation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/paddypower_scraper/validation.py tests/test_paddy_validation.py
git commit -m "paddypower_scraper.validation: Python port of PaddySchemaValidator"
```

---

## Task 9: `PaddyOutput.from_dict` — read paddypower.json back (TDD)

The arb finder (Plan 3) must *read* `paddypower.json`. Add camelCase→dataclass deserialization to `models.py`.

**Files:**
- Modify: `src/paddypower_scraper/models.py`
- Test: `tests/test_paddy_models.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_paddy_models.py`:
```python
"""Round-trip tests for PaddyOutput.from_dict (camelCase JSON → dataclasses)."""

from __future__ import annotations

from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)


def _payload() -> dict:
    return {
        "scrapedAt": "2026-05-25T17:05:58.384555Z",
        "raceCount": 1,
        "races": [
            {
                "venue": "Ballinrobe",
                "country": "IE",
                "offTime": "2026-05-25T18:05:00+01:00",
                "marketName": "18:05 Ballinrobe",
                "raceUrl": "https://example/race",
                "scrapedAt": "2026-05-25T17:05:58.384555Z",
                "betfairWinMarketId": "1.258528220",
                "eachWayTerms": {"fraction": 0.2, "places": 3},
                "runners": [
                    {"name": "Sony Bill", "selectionId": 66986352,
                     "winPrice": 2.72, "winPriceRaw": "7/4"},
                    {"name": "Spare", "selectionId": None,
                     "winPrice": None, "winPriceRaw": None},
                ],
            }
        ],
    }


def test_from_dict_full():
    out = PaddyOutput.from_dict(_payload())
    assert out == PaddyOutput(
        scraped_at="2026-05-25T17:05:58.384555Z",
        race_count=1,
        races=[
            PaddyRace(
                venue="Ballinrobe",
                country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                market_name="18:05 Ballinrobe",
                race_url="https://example/race",
                scraped_at="2026-05-25T17:05:58.384555Z",
                betfair_win_market_id="1.258528220",
                each_way_terms=EachWayTerms(fraction=0.2, places=3),
                runners=[
                    PaddyRunner("Sony Bill", 66986352, 2.72, "7/4"),
                    PaddyRunner("Spare", None, None, None),
                ],
            )
        ],
    )


def test_from_dict_null_eachway():
    p = _payload()
    p["races"][0]["eachWayTerms"] = None
    assert PaddyOutput.from_dict(p).races[0].each_way_terms is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_paddy_models.py -q`
Expected: FAIL — `AttributeError: type object 'PaddyOutput' has no attribute 'from_dict'`.

- [ ] **Step 3: Add `from_dict` classmethods to `src/paddypower_scraper/models.py`**

Append the three classmethods (to `EachWayTerms`, `PaddyRunner`, `PaddyRace`, `PaddyOutput`). Add `from __future__ import annotations` is already present; add `from typing import Any` if not present.

```python
    # --- inside EachWayTerms ---
    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "EachWayTerms":
        return cls(fraction=d["fraction"], places=d["places"])
```
```python
    # --- inside PaddyRunner ---
    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyRunner":
        return cls(
            name=d["name"],
            selection_id=d.get("selectionId"),
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )
```
```python
    # --- inside PaddyRace ---
    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyRace":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            race_url=d["raceUrl"],
            scraped_at=d["scrapedAt"],
            betfair_win_market_id=d.get("betfairWinMarketId"),
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[PaddyRunner.from_dict(r) for r in d.get("runners", [])],
        )
```
```python
    # --- inside PaddyOutput ---
    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "PaddyOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[PaddyRace.from_dict(r) for r in d.get("races", [])],
        )
```

> If the dataclasses are `frozen=True` (they are), classmethods are fine — they construct new instances. Ensure `from typing import Any` is imported at the top of the module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_paddy_models.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/paddypower_scraper/models.py tests/test_paddy_models.py
git commit -m "paddypower_scraper.models: add from_dict deserialization"
```

---

## Task 10: Recolor the contract test + add a `validate` entry point

The opt-in `RUN_CONTRACT` test in `tests/test_output.py` shelled out to the Kotlin validator. With a Python validator in-process, it becomes a plain unit test. Also add a `validate.py` entry point mirroring the other scrapers.

**Files:**
- Modify: `tests/test_output.py`
- Create: `src/paddypower_scraper/validate.py`
- Test: `tests/test_paddy_validate_cli.py`

- [ ] **Step 1: Replace the Kotlin contract test**

In `tests/test_output.py`, delete the `TestKotlinValidatorContract` class (the `RUN_CONTRACT`/`subprocess`/`./gradlew` block) and its now-unused imports (`os`, `subprocess`). Add an in-process check instead:

```python
from paddypower_scraper.validation import validate_paddy_output


class TestValidatorAcceptsOwnOutput:
    """The validator must accept what the writer produces (in-process,
    replaces the old cross-language gradle contract test)."""

    def test_written_output_validates(self, tmp_path):
        from paddypower_scraper.models import (
            EachWayTerms, PaddyOutput, PaddyRace, PaddyRunner,
        )
        from paddypower_scraper.output import write_paddypower_json

        out = PaddyOutput(
            scraped_at="2026-05-25T17:05:58.384555Z",
            race_count=1,
            races=[PaddyRace(
                venue="Ballinrobe", country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                market_name="18:05 Ballinrobe", race_url="https://x/r",
                scraped_at="2026-05-25T17:05:58.384555Z",
                betfair_win_market_id="1.258528220",
                each_way_terms=EachWayTerms(0.2, 3),
                runners=[PaddyRunner("Sony Bill", 66986352, 2.72, "7/4")],
            )],
        )
        target = tmp_path / "paddypower.json"
        write_paddypower_json(out, target)
        assert validate_paddy_output(target.read_text()) == []
```

- [ ] **Step 2: Confirm the `contract` marker is gone**

Run: `grep -rn "RUN_CONTRACT\|gradlew\|mark.contract" tests/`
Expected: no matches. (The marker was already dropped from `pyproject.toml` in Task 1.)

- [ ] **Step 3: Write the failing CLI test**

`tests/test_paddy_validate_cli.py`:
```python
"""Tests for `python -m paddypower_scraper.validate`."""

from __future__ import annotations

from paddypower_scraper.validate import main


def _write_valid(path):
    path.write_text(
        '{"scrapedAt":"2026-05-25T17:05:58Z","raceCount":0,"races":[]}'
    )


def test_valid_file_exit_0(tmp_path, capsys):
    f = tmp_path / "paddypower.json"
    _write_valid(f)
    assert main([str(f)]) == 0
    assert "VALID" in capsys.readouterr().out


def test_invalid_file_exit_1(tmp_path):
    f = tmp_path / "paddypower.json"
    f.write_text('{"scrapedAt":"nope","raceCount":0,"races":[]}')
    assert main([str(f)]) == 1


def test_missing_file_exit_2(tmp_path):
    assert main([str(tmp_path / "nope.json")]) == 2
```

- [ ] **Step 4: Run the CLI test to verify it fails**

Run: `uv run pytest tests/test_paddy_validate_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: paddypower_scraper.validate`.

- [ ] **Step 5: Implement `src/paddypower_scraper/validate.py`**

```python
"""Validate a paddypower.json file against the schema.

Usage: python -m paddypower_scraper.validate [paddypower.json]
Exit 0 = valid, 1 = validation errors, 2 = file error."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_paddy_output


def main(argv: "list[str] | None" = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("paddypower.json")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    errors = validate_paddy_output(path.read_text())
    if not errors:
        print(f"{path}: VALID (matches spec)")
        return 0
    print(f"{path}: INVALID ({len(errors)} errors)")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — all `common` tests + the entire PaddyPower suite (browser smoke skipped). No gradle/Kotlin references remain in tests.

- [ ] **Step 7: Commit**

```bash
git add src/paddypower_scraper/validate.py tests/test_output.py tests/test_paddy_validate_cli.py
git commit -m "paddypower: in-process validator contract test + validate entry point"
```

---

## Plan 1 self-review checklist (run before moving to Plan 2)

- [ ] `uv run pytest -q` is fully green.
- [ ] `grep -rn "Kotlin\|gradlew\|RUN_CONTRACT" tests/` returns only neutral/updated comments.
- [ ] `paddypower-py/` directory no longer exists; PaddyPower code lives under `src/paddypower_scraper/`.
- [ ] `common` exports: `regions.parse_regions/countries_for_all/REGION_COUNTRIES`, `markettype.MarketType/top_n_from_places`, `isovalid.is_iso_utc/is_iso_offset_datetime`, `timeutil.utc_to_london/iso_utc`, `jsonio.to_camel_dict/write_json`.
- [ ] The Kotlin tree is still present (deleted in Plan 3). Plan 2 (Betfair) can begin.
