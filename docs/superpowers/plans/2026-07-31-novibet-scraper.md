# Novibet Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Novibet as a third bookie — `novibet.json` (complete card) → `novibethorses.json` (priced each-way arbs against the shared Betfair lay scrape) — wired into `run.sh`, `publish.sh` and the published web page, and collapse `arb_finder`'s copy-per-bookie duplication into one generic path.

**Architecture:** A new `src/novibet_scraper/` package mirroring `src/sport888_scraper/`'s module shape: pure parsers (`overview.py`, `racecard.py`) fed by an injectable headless-Chromium `BrowserSession`, serialized through `common.jsonio`. Novibet carries no Betfair ids, so it reuses `arb_finder/matching.py`'s off-time + normalized-name join exactly as 888 does. Before any of that, `arb_finder` is refactored so one `PricedHorse`/`BookiePriceLeg` and one join serve all three bookies, with output bytes proven unchanged.

**Tech Stack:** Python ≥ 3.11, `uv`, Playwright (Chromium), pytest. No new dependencies.

## Global Constraints

- **Design spec:** `docs/superpowers/specs/2026-07-31-novibet-scraper-design.md`. Read it before Task 1.
- **Fixtures are already committed** under `tests/fixtures/` (commit `0336e08`). Do not re-capture them. `tests/fixtures/novibet_README.md` documents what each exercises.
- **The each-way category `sysname` is wrong on Place Boost races. Parse the `caption`.** `1/(\d+)\s*-\s*(\d+)\s*Places?` handles both `E/W …` and `Place Boost …`. There is no sysname fallback by design.
- **`horses.json` and `888horses.json` must stay byte-identical** through the `arb_finder` refactor. Task 1 builds the harness that proves it; it must stay green through Tasks 2–3.
- Region ids are the existing CLI tokens `gb-ie` and `us` (`common.regions.parse_regions`). Novibet's own country captions are `GB`/`IRE`/`USA`.
- Python identifiers cannot start with a digit — the package is `novibet_scraper` and the files are `novibet.json` / `novibethorses.json`.
- Run `uv run pytest -q` before every commit. Baseline at plan time: **364 passed, 3 skipped**.
- Every commit message ends with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## File Structure

**New — `src/novibet_scraper/`** (mirrors `sport888_scraper/`):

| File | Responsibility |
|---|---|
| `api.py` | Endpoint constants, warmup URL, `racecard_url()`, `x-gw-*` headers. No I/O. |
| `regions.py` | Region id → Novibet country captions. Pure. |
| `models.py` | `EachWayTerms`, `NovibetRunner`, `NovibetRace`, `NovibetOutput`, `NovibetStub`. |
| `overview.py` | Day index payload → `list[NovibetStub]`. Pure. |
| `racecard.py` | Racecard payload → `NovibetRace | None`. Pure. **Caption-based each-way parsing lives here.** |
| `output.py` | `write_novibet_json()` via `common.jsonio`. |
| `validation.py` / `validate.py` | `novibet.json` schema validator + CLI. |
| `browser.py` | Playwright session: warmup, then `fetch_json()` with `x-gw-*` headers. |
| `cli.py` / `__main__.py` | `python -m novibet_scraper [regions]`. |

**Modified — `src/arb_finder/`:**

| File | Change |
|---|---|
| `bookies.py` (new) | `Bookie` dataclass + registry. The single place a bookie's JSON key names and default paths are declared. |
| `models.py` | `PaddyPriceLeg`+`Sport888PriceLeg` → `BookiePriceLeg`; `Horse`+`Horse888` → `PricedHorse`; `HorsesOutput`+`Horses888Output` → `BookieHorsesOutput`; two rename maps → `build_rename(bookie)`. |
| `calculator.py` | Both joins return `list[PricedHorse]`. |
| `cli.py` | `--source` becomes a registry lookup over one `_run()`. |
| `validation.py` | `validate_horses_output(text, *, bookie=PADDYPOWER)`. |

**Modified — `src/common/`:**

| File | Change |
|---|---|
| `scrapevalidation.py` (new) | Shared bookie-scrape schema validator, parameterised by the extra race-level string fields a bookie requires. |

**Modified — existing validators:** `src/paddypower_scraper/validation.py` and `src/sport888_scraper/validation.py` become thin delegations to the shared core (see Task 9).

**Modified — repo root:** `run.sh`, `publish.sh`, `index.html`, `.gitignore`, `pyproject.toml`, `README.md`.

---

## Phase A — `arb_finder` unification

### Task 1: Byte-exactness harness

Locks the current output bytes through the public CLI entry point, so the refactor in Tasks 2–3 cannot silently change `horses.json` or `888horses.json`. Written against `cli.main()` deliberately — internal class names change in Task 2, the CLI contract does not.

**Files:**
- Test: `tests/test_arb_finder_golden_bytes.py` (create)

**Interfaces:**
- Consumes: `arb_finder.cli.main(argv, *, now)` — existing signature, returns `int`.
- Produces: nothing importable; a regression gate for Tasks 2–3.

- [ ] **Step 1: Write the failing test**

```python
"""Byte-exactness gate for the arb_finder outputs.

The bookie-unification refactor must not change a single byte of
horses.json or 888horses.json. These tests drive cli.main() — the public
contract — so they survive the internal renames the refactor performs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arb_finder import cli

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _betfair_json() -> str:
    return json.dumps({
        "scrapedAt": "2026-07-31T11:59:01Z",
        "raceCount": 1,
        "races": [{
            "raceId": "1.1",
            "venue": "Goodwood",
            "country": "GB",
            "offTime": "2026-07-31T14:00:00+01:00",
            "winMarketUrl": "https://www.betfair.com/exchange/plus/horse-racing/market/1.1",
            "marketName": "14:00 Goodwood - 7f Hcap",
            "marketScrapedAt": {"WIN": "2026-07-31T11:59:02Z",
                                "TOP_3": "2026-07-31T11:59:03Z"},
            "runners": [{"name": "Marianne Mozart",
                         "lay": {"WIN": 16.0, "TOP_3": 4.1},
                         "selectionId": 12345678}],
        }],
    })


def _paddypower_json() -> str:
    return json.dumps({
        "scrapedAt": "2026-07-31T11:59:05Z",
        "raceCount": 1,
        "races": [{
            "venue": "Goodwood",
            "country": "GB",
            "offTime": "2026-07-31T14:00:00+01:00",
            "marketName": "14:00 Goodwood",
            "raceUrl": "https://www.paddypower.com/horse-racing/1",
            "scrapedAt": "2026-07-31T11:59:05Z",
            "betfairWinMarketId": "1.1",
            "eachWayTerms": {"fraction": 0.2, "places": 3},
            "runners": [{"name": "Marianne Mozart", "selectionId": 12345678,
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    })


def _sport888_json() -> str:
    return json.dumps({
        "scrapedAt": "2026-07-31T11:59:07Z",
        "raceCount": 1,
        "races": [{
            "venue": "Goodwood",
            "country": "uk-and-ireland",
            "offTime": "2026-07-31T13:00:00+00:00",
            "marketName": "Winner Market",
            "scrapedAt": "2026-07-31T11:59:07Z",
            "eachWayTerms": {"fraction": 0.2, "places": 3},
            "runners": [{"name": "Marianne Mozart",
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    })


EXPECTED_HORSES = """{
  "computedAt": "2026-07-31T12:00:00Z",
  "betfairScrapedAt": "2026-07-31T11:59:01Z",
  "paddypowerScrapedAt": "2026-07-31T11:59:05Z",
  "horseCount": 1,
  "horses": [
    {
      "venue": "Goodwood",
      "country": "GB",
      "offTime": "2026-07-31T14:00:00+01:00",
      "marketName": "14:00 Goodwood",
      "betfairWinMarketId": "1.1",
      "runner": {
        "name": "Marianne Mozart",
        "selectionId": 12345678
      },
      "paddypower": {
        "winPrice": 15.0,
        "winPriceRaw": "14/1",
        "eachWayTerms": {
          "fraction": 0.2,
          "places": 3
        }
      },
      "betfair": {
        "winLay": 16.0,
        "placeLay": 4.1,
        "placeMarket": "TOP_3"
      },
      "edge": -0.06783536585365846
    }
  ]
}"""


def test_horses_json_bytes_are_stable(tmp_path: Path):
    bf = tmp_path / "betfair.json"
    pp = tmp_path / "paddypower.json"
    out = tmp_path / "horses.json"
    bf.write_text(_betfair_json())
    pp.write_text(_paddypower_json())

    rc = cli.main([str(bf), str(pp), str(out)], now=lambda: NOW)
    assert rc == 0
    assert out.read_text() == EXPECTED_HORSES


def test_888horses_json_keeps_its_leg_name_and_shape(tmp_path: Path):
    bf = tmp_path / "betfair.json"
    s8 = tmp_path / "888sport.json"
    out = tmp_path / "888horses.json"
    bf.write_text(_betfair_json())
    s8.write_text(_sport888_json())

    rc = cli.main(["--source", "888", str(bf), str(s8), str(out)],
                  now=lambda: NOW)
    assert rc == 0
    text = out.read_text()
    data = json.loads(text)

    # The leg is named for 888, never "paddypower" or "bookie".
    assert list(data.keys()) == [
        "computedAt", "betfairScrapedAt", "sport888ScrapedAt",
        "horseCount", "horses"]
    assert list(data["horses"][0].keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "sport888", "betfair", "edge"]
    assert data["horses"][0]["sport888"]["winPrice"] == 15.0
    # 2-space indent, no trailing newline — common.jsonio's json.dump default.
    assert text.startswith('{\n  "computedAt"')
    assert not text.endswith("\n")
```

- [ ] **Step 2: Run to see it fail (or reveal the true expected bytes)**

Run: `uv run pytest tests/test_arb_finder_golden_bytes.py -v`

Expected: `test_horses_json_bytes_are_stable` FAILS on an assertion diff if any literal above is off (most likely the `edge` float or the `now` plumbing). **This test is a snapshot of current behaviour, not a change to it** — if it fails, correct the literals in the test to match what the current code actually emits, then re-run. Do not change `src/` to satisfy it. `test_888horses_json_keeps_its_leg_name_and_shape` should pass first time.

- [ ] **Step 3: Confirm both pass against unmodified `src/`**

Run: `uv run pytest tests/test_arb_finder_golden_bytes.py -v`
Expected: 2 passed.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: 366 passed, 3 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_arb_finder_golden_bytes.py
git commit -m "test(arb): pin horses.json + 888horses.json output bytes

Snapshot gate taken before the bookie-unification refactor. Drives
cli.main() rather than the models, so it survives the internal renames
the refactor performs and fails loudly if output bytes shift.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Bookie registry + unified models

**Files:**
- Create: `src/arb_finder/bookies.py`
- Modify: `src/arb_finder/models.py` (full rewrite of the horse/leg/output types)
- Test: `tests/test_bookies.py` (create), `tests/test_horses_models.py` + `tests/test_horses888_models.py` (update imports)

**Interfaces:**
- Consumes: `common.jsonio.write_json(obj, rename, path)`, `common.markettype.MarketType`.
- Produces:
  - `arb_finder.bookies.Bookie(key, leg_field, scraped_at_field, default_bookie_input, default_output)` — frozen dataclass
  - `arb_finder.bookies.PADDYPOWER`, `SPORT888`, `BOOKIES: dict[str, Bookie]`
  - `arb_finder.models.BookiePriceLeg(win_price, win_price_raw, each_way_terms)`
  - `arb_finder.models.PricedHorse(venue, country, off_time, market_name, betfair_win_market_id, runner, bookie, betfair, edge)`
  - `arb_finder.models.BookieHorsesOutput(computed_at, betfair_scraped_at, bookie_scraped_at, horse_count, horses)`
  - `arb_finder.models.build_rename(bookie) -> dict[str, str]`
  - `arb_finder.models.write_bookie_horses_json(out, bookie, path) -> None`
  - `Runner` and `BetfairLayLeg` keep their current names and fields.

- [ ] **Step 1: Write the failing test**

`tests/test_bookies.py`:

```python
"""The bookie registry is the single place JSON key names are declared."""

from __future__ import annotations

from common.markettype import MarketType
from arb_finder.bookies import BOOKIES, PADDYPOWER, SPORT888
from arb_finder.models import (
    BetfairLayLeg, BookieHorsesOutput, BookiePriceLeg, PricedHorse, Runner,
    build_rename, write_bookie_horses_json,
)


class _Terms:
    """Structural stand-in for a scraper's EachWayTerms (fraction/places)."""
    def __init__(self, fraction, places):
        self.fraction = fraction
        self.places = places


def test_registry_is_keyed_by_cli_token():
    assert set(BOOKIES) == {"paddypower", "888"}
    assert BOOKIES["paddypower"] is PADDYPOWER
    assert BOOKIES["888"] is SPORT888


def test_paddypower_declares_its_json_names():
    assert PADDYPOWER.leg_field == "paddypower"
    assert PADDYPOWER.scraped_at_field == "paddypowerScrapedAt"
    assert PADDYPOWER.default_bookie_input == "paddypower.json"
    assert PADDYPOWER.default_output == "horses.json"


def test_sport888_declares_its_json_names():
    assert SPORT888.leg_field == "sport888"
    assert SPORT888.scraped_at_field == "sport888ScrapedAt"
    assert SPORT888.default_bookie_input == "888sport.json"
    assert SPORT888.default_output == "888horses.json"


def test_build_rename_maps_the_two_variable_fields():
    r = build_rename(SPORT888)
    assert r["bookie"] == "sport888"
    assert r["bookie_scraped_at"] == "sport888ScrapedAt"
    # shared entries survive
    assert r["off_time"] == "offTime"
    assert r["win_price_raw"] == "winPriceRaw"


def _output() -> BookieHorsesOutput:
    return BookieHorsesOutput(
        computed_at="2026-07-31T12:00:00Z",
        betfair_scraped_at="2026-07-31T11:59:01Z",
        bookie_scraped_at="2026-07-31T11:59:05Z",
        horse_count=1,
        horses=[PricedHorse(
            venue="Goodwood", country="GB",
            off_time="2026-07-31T14:00:00+01:00", market_name="14:00 Goodwood",
            betfair_win_market_id="1.1",
            runner=Runner("Marianne Mozart", 12345678),
            bookie=BookiePriceLeg(15.0, "14/1", _Terms(0.2, 3)),
            betfair=BetfairLayLeg(16.0, 4.1, MarketType.TOP_3),
            edge=0.81)],
    )


def test_writer_uses_the_bookie_leg_name(tmp_path):
    import json
    target = tmp_path / "out.json"
    write_bookie_horses_json(_output(), PADDYPOWER, target)
    data = json.loads(target.read_text())
    assert "paddypower" in data["horses"][0]
    assert "bookie" not in data["horses"][0]
    assert "paddypowerScrapedAt" in data

    write_bookie_horses_json(_output(), SPORT888, target)
    data = json.loads(target.read_text())
    assert "sport888" in data["horses"][0]
    assert "sport888ScrapedAt" in data


def test_field_order_is_unchanged(tmp_path):
    import json
    target = tmp_path / "out.json"
    write_bookie_horses_json(_output(), PADDYPOWER, target)
    data = json.loads(target.read_text())
    assert list(data.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "horseCount", "horses"]
    assert list(data["horses"][0].keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "edge"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_bookies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'arb_finder.bookies'`

- [ ] **Step 3: Write `src/arb_finder/bookies.py`**

```python
"""Per-bookie JSON key names and default paths.

One Bookie entry is the only place a bookie's output naming is declared:
the leg field in each horse, the <bookie>ScrapedAt timestamp, and the
default input/output filenames. Adding a bookie means adding an entry
here, not another model or another CLI branch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bookie:
    key: str                   # --source token
    leg_field: str             # JSON key of the bookie price leg
    scraped_at_field: str      # JSON key of the bookie's scrapedAt
    default_bookie_input: str  # default bookie-scrape input file
    default_output: str        # default priced-arb output file


PADDYPOWER = Bookie(
    key="paddypower",
    leg_field="paddypower",
    scraped_at_field="paddypowerScrapedAt",
    default_bookie_input="paddypower.json",
    default_output="horses.json",
)

SPORT888 = Bookie(
    key="888",
    leg_field="sport888",
    scraped_at_field="sport888ScrapedAt",
    default_bookie_input="888sport.json",
    default_output="888horses.json",
)

BOOKIES: dict[str, Bookie] = {b.key: b for b in (PADDYPOWER, SPORT888)}
```

- [ ] **Step 4: Rewrite `src/arb_finder/models.py`**

Replace the whole file:

```python
"""Dataclasses mirroring the priced-arb output files + serializer.

One set of models serves every bookie. The only per-bookie variation is
JSON key naming, which comes from bookies.Bookie via build_rename()."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.jsonio import write_json
from common.markettype import MarketType

from .bookies import Bookie


class EachWayTermsLike(Protocol):
    """Any scraper's EachWayTerms. Structural on purpose: each scraper
    package owns its own dataclass, and jsonio serializes it by shape."""
    fraction: float
    places: int


@dataclass(frozen=True)
class BookiePriceLeg:
    win_price: float
    win_price_raw: str
    each_way_terms: EachWayTermsLike


@dataclass(frozen=True)
class BetfairLayLeg:
    win_lay: float
    place_lay: float
    place_market: MarketType


@dataclass(frozen=True)
class Runner:
    name: str
    selection_id: int


@dataclass(frozen=True)
class PricedHorse:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: Runner
    bookie: BookiePriceLeg
    betfair: BetfairLayLeg
    edge: float


@dataclass(frozen=True)
class BookieHorsesOutput:
    computed_at: str
    betfair_scraped_at: str
    bookie_scraped_at: str
    horse_count: int
    horses: list[PricedHorse]


_BASE_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
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


def build_rename(bookie: Bookie) -> dict[str, str]:
    """Shared snake→camel map plus the two bookie-specific names."""
    return {
        **_BASE_RENAME,
        "bookie_scraped_at": bookie.scraped_at_field,
        "bookie": bookie.leg_field,
    }


def write_bookie_horses_json(
    out: BookieHorsesOutput, bookie: Bookie, path: Path | str
) -> None:
    write_json(out, build_rename(bookie), path)
```

Note: JSON key *order* comes from dataclass field declaration order, not the rename map — `PricedHorse`'s field order matches the old `Horse`/`Horse888` exactly, which is what keeps the bytes stable.

- [ ] **Step 5: Run the new test**

Run: `uv run pytest tests/test_bookies.py -v`
Expected: 6 passed.

- [ ] **Step 6: Update the two model test files that import the old names**

`tests/test_horses_models.py` and `tests/test_horses888_models.py` construct `Horse`/`HorsesOutput`/`PaddyPriceLeg` and `Horse888`/`Horses888Output`/`Sport888PriceLeg`. Rewrite them to use `PricedHorse`/`BookieHorsesOutput`/`BookiePriceLeg` with `write_bookie_horses_json(out, PADDYPOWER, path)` and `(out, SPORT888, path)` respectively. Keep every existing assertion about emitted JSON keys and values — those are the contract. `tests/test_horses_golden.py` needs the same treatment.

Run: `uv run pytest tests/test_horses_models.py tests/test_horses888_models.py tests/test_horses_golden.py -v`
Expected: all pass.

- [ ] **Step 7: Run the whole suite (calculator/cli still broken — expected)**

Run: `uv run pytest -q`
Expected: failures confined to `tests/test_calculator.py`, `tests/test_horses_cli.py`, `tests/test_horses888_cli.py`, `tests/test_arb_finder_golden_bytes.py`, `tests/test_matching.py` — they import `Horse`/`Horse888`, fixed in Task 3. **Do not commit yet.**

- [ ] **Step 8: Proceed directly to Task 3** (the tree is intentionally red between Tasks 2 and 3; they land as one commit at the end of Task 3).

---

### Task 3: Unified calculator + table-driven CLI

**Files:**
- Modify: `src/arb_finder/calculator.py`, `src/arb_finder/cli.py`, `src/arb_finder/validation.py`
- Test: `tests/test_calculator.py`, `tests/test_horses_cli.py`, `tests/test_horses888_cli.py` (update)

**Interfaces:**
- Consumes: `arb_finder.bookies.{Bookie, BOOKIES, PADDYPOWER, SPORT888}`, `arb_finder.models.{PricedHorse, BookiePriceLeg, BookieHorsesOutput, write_bookie_horses_json}`, `arb_finder.matching.{match_race, match_runner}`.
- Produces:
  - `arb_finder.calculator.find_horses(betfair, paddy) -> list[PricedHorse]`
  - `arb_finder.calculator.find_horses_by_name(betfair, bookie_output) -> tuple[list[PricedHorse], MatchStats]`
  - `arb_finder.calculator.each_way_arb_margin(p, f, bw, bp) -> float` (unchanged)
  - `arb_finder.calculator.MatchStats(races_matched, races_unmatched, runners_priced, runners_unmatched)` (unchanged)
  - `arb_finder.cli.SOURCES: dict[str, SourceSpec]`
  - `arb_finder.validation.validate_horses_output(text, *, bookie=PADDYPOWER) -> list[str]`

- [ ] **Step 1: Update `calculator.py`**

Change only the constructed types — the join logic, ordering and edge maths stay exactly as they are.

In `find_horses`, replace the `Horse(...)` construction with:

```python
            out.append(PricedHorse(
                venue=pr.venue,
                country=pr.country,
                off_time=pr.off_time,
                market_name=pr.market_name,
                betfair_win_market_id=win_market_id,
                runner=Runner(name=prun.name, selection_id=sel),
                bookie=BookiePriceLeg(
                    win_price=pp_price, win_price_raw=pp_raw, each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, place_lay=place_lay, place_market=place_market),
                edge=edge,
            ))
```

In `find_horses_by_name`, rename the parameter `eight88` → `bookie_output` (it now serves 888 and Novibet), retype the return to `tuple[list[PricedHorse], MatchStats]`, and replace the `Horse888(...)` construction with the same `PricedHorse(...)` shape, `bookie=BookiePriceLeg(...)`. Update the imports at the top of the file to:

```python
from .models import BetfairLayLeg, BookiePriceLeg, PricedHorse, Runner
```

and drop the now-unused `Horse`, `Horse888`, `PaddyPriceLeg`, `Sport888PriceLeg` imports and the `sport888_scraper.models.Sport888Output` type-only import (annotate `bookie_output` loosely — any object with `.scraped_at` and `.races` works, which is exactly what makes it reusable).

Update the docstring of `find_horses_by_name` to say "a bookie that carries no Betfair ids (888sport, Novibet)".

- [ ] **Step 2: Rewrite `cli.py` as a registry lookup**

```python
"""Edge calculator entry point. Reads + validates betfair.json and one
bookie's scrape, prices every fully-priced runner, writes that bookie's
horses file. Exit 0 ok (even zero horses), 1 bad usage, 2 input error."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from betfair_scraper.models import ScrapeOutput
from betfair_scraper.validation import validate_scrape_output
from common.timeutil import iso_utc
from paddypower_scraper.models import PaddyOutput
from paddypower_scraper.validation import validate_paddy_output
from sport888_scraper.models import Sport888Output
from sport888_scraper.validation import validate_sport888_output

from .bookies import Bookie, PADDYPOWER, SPORT888
from .calculator import find_horses, find_horses_by_name
from .models import BookieHorsesOutput, write_bookie_horses_json


@dataclass(frozen=True)
class SourceSpec:
    bookie: Bookie
    label: str                              # for error messages
    parse: Callable[[str], Any]             # JSON text -> bookie output model
    validate: Callable[[str], list[str]]    # JSON text -> schema errors
    join: str                               # "ids" | "name"


SOURCES: dict[str, SourceSpec] = {
    "paddypower": SourceSpec(
        bookie=PADDYPOWER, label="PaddyPower",
        parse=lambda t: PaddyOutput.from_dict(json.loads(t)),
        validate=validate_paddy_output, join="ids"),
    "888": SourceSpec(
        bookie=SPORT888, label="888sport",
        parse=lambda t: Sport888Output.from_dict(json.loads(t)),
        validate=validate_sport888_output, join="name"),
}


def parse_cli_args(spec: SourceSpec, argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", spec.bookie.default_bookie_input,
                spec.bookie.default_output)
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    flag = "" if spec.bookie.key == "paddypower" else f" --source {spec.bookie.key}"
    raise ValueError(
        f"usage: arb-finder{flag}"
        f"                                # all defaults\n"
        f"       arb-finder{flag} <betfair-in> <bookie-in> <out>  # all explicit"
    )


def main(argv=None, *, now=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = "paddypower"
    if "--source" in argv:
        i = argv.index("--source")
        try:
            source = argv[i + 1]
        except IndexError:
            print(f"--source requires a value ({'|'.join(SOURCES)})", file=sys.stderr)
            return 1
        del argv[i:i + 2]
    spec = SOURCES.get(source)
    if spec is None:
        print(f"unknown --source {source}; valid: {', '.join(SOURCES)}",
              file=sys.stderr)
        return 1
    return _run(spec, argv, now)


def _run(spec: SourceSpec, argv: list[str], now) -> int:
    try:
        betfair_in, bookie_in, out_path = parse_cli_args(spec, argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    betfair_text = _read_or_none(betfair_in)
    if betfair_text is None:
        return 2
    bookie_text = _read_or_none(bookie_in)
    if bookie_text is None:
        return 2

    betfair_errors = validate_scrape_output(betfair_text)
    if betfair_errors:
        print(f"Error: {betfair_in} fails Betfair schema:", file=sys.stderr)
        for e in betfair_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    bookie_errors = spec.validate(bookie_text)
    if bookie_errors:
        print(f"Error: {bookie_in} fails {spec.label} schema:", file=sys.stderr)
        for e in bookie_errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    bookie_out = spec.parse(bookie_text)

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    if spec.join == "ids":
        horses = find_horses(betfair, bookie_out)
        stats = None
    else:
        horses, stats = find_horses_by_name(betfair, bookie_out)

    output = BookieHorsesOutput(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        bookie_scraped_at=bookie_out.scraped_at,
        horse_count=len(horses),
        horses=horses,
    )
    write_bookie_horses_json(output, spec.bookie, out_path)

    if stats is None:
        print(f"Wrote {out_path} ({len(horses)} horses from "
              f"{len(betfair.races)} BF races and "
              f"{len(bookie_out.races)} PP races)")
    else:
        print(f"Wrote {out_path} ({len(horses)} horses; races matched "
              f"{stats.races_matched}/"
              f"{stats.races_matched + stats.races_unmatched}, "
              f"runners unmatched {stats.runners_unmatched})")
    return 0


def _read_or_none(path: str) -> "str | None":
    p = Path(path)
    if not p.exists():
        print(f"Error: input file not found: {path}", file=sys.stderr)
        return None
    try:
        return p.read_text()
    except OSError as e:
        print(f"Error: failed to read {path}: {e}", file=sys.stderr)
        return None
```

- [ ] **Step 3: Make `validation.py` bookie-aware**

`validate_horses_output` currently hardcodes `paddypowerScrapedAt` and the `paddypower` leg. Give it a keyword-only `bookie` argument defaulting to `PADDYPOWER` so every existing caller is unchanged:

```python
from .bookies import Bookie, PADDYPOWER

def validate_horses_output(text: str, *, bookie: Bookie = PADDYPOWER) -> list[str]:
```

Inside, replace the literal `"paddypowerScrapedAt"` in the required-keys loop with `bookie.scraped_at_field`, and `h.get("paddypower")` / the `f"{ctx}.paddypower"` context string with `h.get(bookie.leg_field)` / `f"{ctx}.{bookie.leg_field}"`. Rename `_validate_paddy_leg` to `_validate_bookie_leg` (its body is unchanged). Everything else stays.

- [ ] **Step 4: Update the affected tests**

`tests/test_calculator.py` and `tests/test_matching.py` reference `Horse`/`Horse888` and `find_horses_by_name(betfair, eight88)`. Update imports to `PricedHorse` and assert `h.bookie.win_price` where they previously asserted `h.paddypower.win_price` / `h.sport888.win_price`. Do not change any expected numeric value — the maths is untouched.

`tests/test_horses_cli.py` and `tests/test_horses888_cli.py` drive `cli.main()` and assert on emitted JSON — they should need no change beyond any direct model imports.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: 372 passed, 3 skipped (366 plus the 6 new `test_bookies.py` tests), assuming the Task 2 Step 6 rewrites kept their test counts. The exact total matters less than two things: **zero failures**, and **`tests/test_arb_finder_golden_bytes.py` green** — that is the whole point of the refactor. If it fails, the refactor changed output bytes: fix `src/`, never the expected literals.

- [ ] **Step 6: Commit Tasks 2 + 3 together**

```bash
git add src/arb_finder tests/test_bookies.py tests/test_horses_models.py \
        tests/test_horses888_models.py tests/test_horses_golden.py \
        tests/test_calculator.py tests/test_matching.py
git commit -m "refactor(arb): one PricedHorse + bookie registry for every bookie

Collapses PaddyPriceLeg/Sport888PriceLeg into BookiePriceLeg, Horse/Horse888
into PricedHorse, HorsesOutput/Horses888Output into BookieHorsesOutput, and
the two hand-written rename maps into build_rename(bookie). --source is now
a lookup over one _run(); validate_horses_output takes a bookie.

Adding a bookie is now a registry entry rather than a third copy of the
models, the join and the CLI branch. horses.json and 888horses.json bytes
are unchanged, held by tests/test_arb_finder_golden_bytes.py.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase B — the `novibet_scraper` package

### Task 4: Package skeleton, regions, packaging

**Files:**
- Create: `src/novibet_scraper/__init__.py` (empty), `src/novibet_scraper/regions.py`
- Modify: `pyproject.toml`
- Test: `tests/test_novibet_regions.py`, `tests/test_novibet_packaging.py` (create)

**Interfaces:**
- Produces: `novibet_scraper.regions.REGION_COUNTRIES: dict[str, frozenset[str]]`, `novibet_scraper.regions.countries_for_all(region_ids: frozenset[str]) -> frozenset[str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_novibet_regions.py`:

```python
from common.regions import parse_regions
from novibet_scraper.regions import REGION_COUNTRIES, countries_for_all


def test_gb_ie_maps_to_novibets_own_captions():
    # Novibet says "IRE", not Betfair's "IE".
    assert REGION_COUNTRIES["gb-ie"] == frozenset({"GB", "IRE"})


def test_us_maps_to_usa():
    assert REGION_COUNTRIES["us"] == frozenset({"USA"})


def test_countries_for_all_unions():
    assert countries_for_all(parse_regions("gb-ie,us")) == frozenset(
        {"GB", "IRE", "USA"})


def test_unknown_region_id_contributes_nothing():
    assert countries_for_all(frozenset({"mars"})) == frozenset()
```

`tests/test_novibet_packaging.py`:

```python
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wheel_includes_novibet_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/novibet_scraper" in pkgs


def test_script_entry_present():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["novibet-scraper"] == "novibet_scraper.cli:main"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_novibet_regions.py tests/test_novibet_packaging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper'` and two `KeyError`s.

- [ ] **Step 3: Create the package**

`src/novibet_scraper/__init__.py` — empty file.

`src/novibet_scraper/regions.py`:

```python
"""Region id → Novibet country caption(s). Pure, no I/O.

Novibet's day index groups by its own country captions, which are close to
but not identical to Betfair's country codes: Novibet says "IRE" and "USA"
where Betfair says "IE" and "US". This map is Novibet-specific and
deliberately separate from common.regions."""

from __future__ import annotations

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "gb-ie": frozenset({"GB", "IRE"}),
    "us": frozenset({"USA"}),
}


def countries_for_all(region_ids: frozenset[str]) -> frozenset[str]:
    """Union of Novibet country captions for every region id. Assumes ids
    are valid (caller validates first via common.regions.parse_regions)."""
    out: set[str] = set()
    for rid in region_ids:
        out |= REGION_COUNTRIES.get(rid, frozenset())
    return frozenset(out)
```

- [ ] **Step 4: Register the package in `pyproject.toml`**

Add `novibet-scraper = "novibet_scraper.cli:main"` to `[project.scripts]` and `"src/novibet_scraper",` to `[tool.hatch.build.targets.wheel] packages`.

(The script entry points at a `cli:main` that does not exist until Task 11. That is fine — it is metadata, not an import.)

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_novibet_regions.py tests/test_novibet_packaging.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/novibet_scraper pyproject.toml tests/test_novibet_regions.py \
        tests/test_novibet_packaging.py
git commit -m "feat(novibet): package skeleton + region caption map

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `api.py` — endpoints, headers, URL builder

**Files:**
- Create: `src/novibet_scraper/api.py`
- Test: `tests/test_novibet_api.py` (create)

**Interfaces:**
- Produces: `novibet_scraper.api.{USER_AGENT, LOCALE, TIMEZONE, WARMUP_URL, OVERVIEW_URL, API_HEADERS}` and `racecard_url(bet_context_id: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
from novibet_scraper import api


def test_warmup_is_the_horse_racing_page():
    assert api.WARMUP_URL == "https://www.novibet.ie/sports/horse-racing/4372612"


def test_overview_url_targets_the_day_index():
    assert api.OVERVIEW_URL.startswith(
        "https://www.novibet.ie/spt/feed/marketviews/horse-racing-overview2/4324/4372612")
    assert "lang=en-IE" in api.OVERVIEW_URL
    assert "usrGrp=IE" in api.OVERVIEW_URL


def test_racecard_url_embeds_the_bet_context_id():
    url = api.racecard_url("47383682")
    assert url.startswith(
        "https://www.novibet.ie/spt/feed/marketviews/horse-racing-race2/4324/47383682")
    assert "lang=en-IE" in url


def test_racecard_url_escapes_its_argument():
    assert "a/b" not in api.racecard_url("a/b")


def test_gateway_headers_are_sent():
    # A bare fetch without the x-gw-* set is rejected by the gateway.
    for key in ("x-gw-domain-key", "x-gw-application-name", "x-gw-country-sysname",
                "x-gw-language-sysname", "x-gw-channel", "x-gw-client-layout",
                "x-gw-cms-key", "x-gw-currency-sysname", "x-gw-client-timezone",
                "x-gw-odds-representation"):
        assert key in api.API_HEADERS, f"missing gateway header {key}"
    assert api.API_HEADERS["accept"].startswith("application/json")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'api'`

- [ ] **Step 3: Write `src/novibet_scraper/api.py`**

```python
"""Novibet endpoint constants and URL builders. No I/O.

Both feeds sit behind Cloudflare: a bare request is answered with a 403
challenge page, so browser.py warms up on WARMUP_URL first and then fetches
from inside the page. The x-gw-* headers are required by the gateway."""

from __future__ import annotations

from urllib.parse import quote

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
LOCALE = "en-IE"
TIMEZONE = "Europe/Dublin"

_BASE = "https://www.novibet.ie"
_SPORT_ID = "4324"           # horse racing
_GROUP_ID = "4372612"        # HORSE_RACING market-view group
_QUERY = "?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE"

# Warmup page — clears Cloudflare and seeds the session cookies.
WARMUP_URL = f"{_BASE}/sports/horse-racing/{_GROUP_ID}"

# Full-day index: days → countries → meetings → races.
OVERVIEW_URL = (
    f"{_BASE}/spt/feed/marketviews/horse-racing-overview2/"
    f"{_SPORT_ID}/{_GROUP_ID}{_QUERY}&timestamp=undefined"
)

_RACECARD_BASE = f"{_BASE}/spt/feed/marketviews/horse-racing-race2/{_SPORT_ID}/"

API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "x-gw-domain-key": "_IE",
    "x-gw-cms-key": "_IE",
    "x-gw-application-name": "NoviIE",
    "x-gw-currency-sysname": "EUR",
    "x-gw-country-sysname": "IE",
    "x-gw-language-sysname": "en-IE",
    "x-gw-client-timezone": "Europe/Dublin",
    "x-gw-channel": "WebPC",
    "x-gw-client-layout": "Desktop",
    "x-gw-odds-representation": "Fractional",
}


def racecard_url(bet_context_id: str) -> str:
    """Build a racecard URL for one Novibet betContextId."""
    return f"{_RACECARD_BASE}{quote(str(bet_context_id), safe='')}{_QUERY}"
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_novibet_api.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/novibet_scraper/api.py tests/test_novibet_api.py
git commit -m "feat(novibet): endpoint constants + racecard URL builder

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `models.py`

**Files:**
- Create: `src/novibet_scraper/models.py`
- Test: `tests/test_novibet_models.py` (create)

**Interfaces:**
- Produces:
  - `EachWayTerms(fraction: float, places: int)` + `from_dict`
  - `NovibetRunner(name, win_price, win_price_raw)` + `from_dict`
  - `NovibetRace(venue, country, off_time, market_name, scraped_at, each_way_terms, runners)` + `from_dict`
  - `NovibetOutput(scraped_at, race_count, races)` + `from_dict`
  - `NovibetStub(bet_context_id, venue, country, start_time_utc)` — internal, not serialized

- [ ] **Step 1: Write the failing test**

```python
from novibet_scraper.models import (
    EachWayTerms, NovibetOutput, NovibetRace, NovibetRunner, NovibetStub,
)


def test_round_trips_a_full_payload():
    out = NovibetOutput.from_dict({
        "scrapedAt": "2026-07-31T12:00:00Z",
        "raceCount": 1,
        "races": [{
            "venue": "Wolverhampton",
            "country": "GB",
            "offTime": "2026-07-31T13:00:00+00:00",
            "marketName": "Race Winner",
            "scrapedAt": "2026-07-31T12:00:00Z",
            "eachWayTerms": {"fraction": 0.2, "places": 3},
            "runners": [{"name": "Marianne Mozart",
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    })
    assert out.scraped_at == "2026-07-31T12:00:00Z"
    assert out.race_count == 1
    race = out.races[0]
    assert race.venue == "Wolverhampton"
    assert race.country == "GB"
    assert race.off_time == "2026-07-31T13:00:00+00:00"
    assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)
    assert race.runners[0] == NovibetRunner(
        name="Marianne Mozart", win_price=15.0, win_price_raw="14/1")


def test_missing_each_way_terms_is_none():
    race = NovibetRace.from_dict({
        "venue": "Musselburgh", "country": "GB",
        "offTime": "2026-07-31T17:15:00+00:00", "marketName": "Race Winner",
        "scrapedAt": "2026-07-31T12:00:00Z", "eachWayTerms": None, "runners": [],
    })
    assert race.each_way_terms is None
    assert race.runners == []


def test_runner_prices_may_be_null():
    r = NovibetRunner.from_dict({"name": "Suspended"})
    assert r.win_price is None and r.win_price_raw is None


def test_stub_is_a_plain_record():
    s = NovibetStub(bet_context_id="47383682", venue="Wolverhampton",
                    country="GB", start_time_utc="2026-07-31T13:00:00+00:00")
    assert s.bet_context_id == "47383682"
    assert s.country == "GB"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.models'`

- [ ] **Step 3: Write `src/novibet_scraper/models.py`**

```python
"""Dataclasses mirroring novibet.json. snake_case here; the
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
class NovibetRunner:
    name: str
    win_price: float | None
    win_price_raw: str | None

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "NovibetRunner":
        return cls(
            name=d["name"],
            win_price=d.get("winPrice"),
            win_price_raw=d.get("winPriceRaw"),
        )


@dataclass(frozen=True)
class NovibetRace:
    venue: str
    country: str  # Novibet's own caption, e.g. "GB" / "IRE" / "USA"
    off_time: str
    market_name: str
    scraped_at: str
    each_way_terms: EachWayTerms | None
    runners: list[NovibetRunner] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "NovibetRace":
        ew = d.get("eachWayTerms")
        return cls(
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            market_name=d["marketName"],
            scraped_at=d["scrapedAt"],
            each_way_terms=EachWayTerms.from_dict(ew) if ew is not None else None,
            runners=[NovibetRunner.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class NovibetOutput:
    scraped_at: str
    race_count: int
    races: list[NovibetRace] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: "dict[str, Any]") -> "NovibetOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[NovibetRace.from_dict(r) for r in d.get("races", [])],
        )


@dataclass(frozen=True)
class NovibetStub:
    """Internal: metadata-only race entry from the day index.
    Not emitted in novibet.json."""
    bet_context_id: str
    venue: str
    country: str
    start_time_utc: str
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_novibet_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/novibet_scraper/models.py tests/test_novibet_models.py
git commit -m "feat(novibet): data models mirroring novibet.json

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `overview.py` — day index → stubs

**Files:**
- Create: `src/novibet_scraper/overview.py`
- Modify: `tests/conftest.py` (add fixtures)
- Test: `tests/test_novibet_overview.py` (create)

**Interfaces:**
- Consumes: `novibet_scraper.models.NovibetStub`
- Produces: `novibet_scraper.overview.parse_overview(payload: dict) -> list[NovibetStub]`

Region and day filtering are the CLI's job — this returns every well-formed stub from every day in the payload, exactly as `sport888_scraper.schedule.parse_schedule` does.

- [ ] **Step 1: Add the fixtures to `tests/conftest.py`**

Append:

```python
@pytest.fixture
def novibet_overview_payload() -> dict:
    """Raw Novibet day-index response (2 days: Jul 31 + Aug 01, 2026)."""
    return _load("novibet_overview.json")


@pytest.fixture
def novibet_racecard_3pl() -> dict:
    """Wolverhampton 13:00 — 10 runners, E/W 1/5 - 3 Places, sysname agrees."""
    return _load("novibet_racecard_ew_3pl_1_5.json")


@pytest.fixture
def novibet_racecard_2pl() -> dict:
    """Goodwood 13:25 — 7 runners, E/W 1/4 - 2 Places."""
    return _load("novibet_racecard_ew_2pl_1_4.json")


@pytest.fixture
def novibet_racecard_boost_mismatch_4pl() -> dict:
    """Goodwood 14:35 — caption says 4 places 1/5, sysname says 3_4."""
    return _load("novibet_racecard_ew_4pl_1_5_boost_mismatch.json")


@pytest.fixture
def novibet_racecard_boost_mismatch_5pl() -> dict:
    """Galway 17:35 — caption says 5 places 1/5, sysname says 2_5."""
    return _load("novibet_racecard_ew_5pl_1_5_boost_mismatch.json")


@pytest.fixture
def novibet_racecard_6pl() -> dict:
    """Goodwood 14:00 — 6 places (unpriceable), 4 non-runners on the card."""
    return _load("novibet_racecard_ew_6pl_1_5_boost.json")


@pytest.fixture
def novibet_racecard_no_eachway() -> dict:
    """Musselburgh 17:15 — 5-runner field, no each-way market offered."""
    return _load("novibet_racecard_no_eachway.json")


@pytest.fixture
def novibet_racecard_near_off() -> dict:
    """Goodwood 12:50 — 1 min from off; each-way pulled, win market live."""
    return _load("novibet_racecard_near_off.json")


@pytest.fixture
def novibet_racecard_no_markets() -> dict:
    """Fairview at the off — marketCategories is empty."""
    return _load("novibet_racecard_no_markets.json")
```

- [ ] **Step 2: Write the failing test**

`tests/test_novibet_overview.py`:

```python
from novibet_scraper.models import NovibetStub
from novibet_scraper.overview import parse_overview


class TestParseOverview:
    def test_returns_every_race_across_both_days(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        # 59 races on Jul 31 + 17 on Aug 01
        assert len(stubs) == 76
        assert all(isinstance(s, NovibetStub) for s in stubs)

    def test_first_stub_carries_id_venue_country_and_time(
            self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        first = next(s for s in stubs if s.bet_context_id == "47383594")
        assert first.venue == "Goodwood"
        assert first.country == "GB"
        assert first.start_time_utc == "2026-07-31T12:50:00+00:00"

    def test_bet_context_id_is_a_string(self, novibet_overview_payload):
        # The feed sends it as an int; the racecard URL builder needs a str.
        stubs = parse_overview(novibet_overview_payload)
        assert all(isinstance(s.bet_context_id, str) for s in stubs)

    def test_country_captions_are_novibets_own(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        assert {"GB", "IRE", "USA", "SAF", "GER", "AUS"} >= {
            s.country for s in stubs}

    def test_gb_day_one_count(self, novibet_overview_payload):
        stubs = parse_overview(novibet_overview_payload)
        gb_today = [s for s in stubs
                    if s.country == "GB" and s.start_time_utc.startswith("2026-07-31")]
        assert len(gb_today) == 41

    def test_empty_and_malformed_payloads_yield_nothing(self):
        assert parse_overview({}) == []
        assert parse_overview({"days": None}) == []
        assert parse_overview({"days": [{"countries": [{"meetings": [{}]}]}]}) == []

    def test_incomplete_entries_are_dropped(self):
        payload = {"days": [{"countries": [{"caption": "GB", "meetings": [{
            "caption": "Goodwood",
            "races": [
                {"betContextId": 1, "startTimeUTC": "2026-07-31T12:50:00+00:00"},
                {"betContextId": 2},                       # no start time
                {"startTimeUTC": "2026-07-31T13:00:00+00:00"},  # no id
            ]}]}]}]}
        stubs = parse_overview(payload)
        assert [s.bet_context_id for s in stubs] == ["1"]
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_overview.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.overview'`

- [ ] **Step 4: Write `src/novibet_scraper/overview.py`**

```python
"""Parse the horse-racing-overview2 day index into race stubs.

The payload nests days → countries → meetings → races. Venue lives on the
meeting, the country caption on the country, and the id/off-time on the
race. Day and region filtering are the CLI's job, so this returns every
well-formed stub from every day in the payload."""

from __future__ import annotations

from .models import NovibetStub


def parse_overview(payload: dict) -> list[NovibetStub]:
    """One NovibetStub per race entry that has both a betContextId and a
    startTimeUTC, plus a venue and country caption. Drops anything else."""
    days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(days, list):
        return []
    out: list[NovibetStub] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        for country in day.get("countries") or []:
            if not isinstance(country, dict):
                continue
            country_caption = country.get("caption")
            if not (isinstance(country_caption, str) and country_caption):
                continue
            for meeting in country.get("meetings") or []:
                if not isinstance(meeting, dict):
                    continue
                venue = meeting.get("caption")
                if not (isinstance(venue, str) and venue):
                    continue
                for race in meeting.get("races") or []:
                    if not isinstance(race, dict):
                        continue
                    bcid = race.get("betContextId")
                    bcid = (str(bcid)
                            if isinstance(bcid, (str, int)) and str(bcid)
                            else None)
                    start = race.get("startTimeUTC")
                    if not (bcid and isinstance(start, str) and start):
                        continue
                    out.append(NovibetStub(
                        bet_context_id=bcid,
                        venue=venue,
                        country=country_caption,
                        start_time_utc=start,
                    ))
    return out
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_novibet_overview.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/novibet_scraper/overview.py tests/test_novibet_overview.py tests/conftest.py
git commit -m "feat(novibet): day-index parser -> race stubs

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `racecard.py` — the caption-based each-way parser

**The highest-risk task in the plan.** Getting the each-way terms wrong does not crash anything; it silently reports arbs that do not exist. Read the "The data source" section of the spec before starting.

**Files:**
- Create: `src/novibet_scraper/racecard.py`
- Test: `tests/test_novibet_racecard.py` (create)

**Interfaces:**
- Consumes: `novibet_scraper.models.{EachWayTerms, NovibetRace, NovibetRunner}`
- Produces:
  - `novibet_scraper.racecard.parse_racecard(payload: dict, scraped_at_utc: str, *, venue: str, country: str) -> NovibetRace | None`
  - `novibet_scraper.racecard.parse_each_way_caption(caption: str) -> EachWayTerms | None`

`venue`/`country` are passed in from the stub rather than read from the payload: the day index is already the authority for both, and it is what region filtering ran against.

- [ ] **Step 1: Write the failing test**

```python
"""The each-way terms come from the market category CAPTION.

The sysname (HORSE_RACING_RACE_WINNER_EACHWAY_<places>_<divisor>) is wrong
on Place Boost races — 5 of 30 GB/IRE races on the capture day. Trusting it
inflates the place fraction AND picks the wrong Betfair TOP_N market, both
biased toward reporting arbs that are not there. See
tests/fixtures/novibet_README.md."""

from __future__ import annotations

from novibet_scraper.models import EachWayTerms, NovibetRace
from novibet_scraper.racecard import parse_each_way_caption, parse_racecard
from conftest import mutate  # repo convention: tests/ is not a package

SCRAPED = "2026-07-31T12:00:00Z"


def _parse(payload, venue="Goodwood", country="GB"):
    return parse_racecard(payload, SCRAPED, venue=venue, country=country)


class TestParseEachWayCaption:
    def test_plain_each_way(self):
        assert parse_each_way_caption("E/W 1/5 - 3 Places") == EachWayTerms(0.2, 3)

    def test_quarter_odds_two_places(self):
        assert parse_each_way_caption("E/W 1/4 - 2 Places") == EachWayTerms(0.25, 2)

    def test_place_boost_prefix(self):
        assert parse_each_way_caption("Place Boost 1/5 - 4 Places") == EachWayTerms(0.2, 4)

    def test_singular_place(self):
        assert parse_each_way_caption("E/W 1/4 - 1 Place") == EachWayTerms(0.25, 1)

    def test_unparseable_returns_none(self):
        for bad in ("", "Race Winner", "E/W", "1/5", "Insurebet - 2 Places",
                    "E/W 1/0 - 3 Places"):
            assert parse_each_way_caption(bad) is None, bad


class TestEachWayTermsFollowTheCaption:
    def test_agreeing_sysname(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)

    def test_two_places(self, novibet_racecard_2pl):
        race = _parse(novibet_racecard_2pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.25, places=2)

    def test_boost_mismatch_4pl_follows_caption_not_sysname(
            self, novibet_racecard_boost_mismatch_4pl):
        # sysname says 3 places at 1/4; the caption says 4 places at 1/5.
        race = _parse(novibet_racecard_boost_mismatch_4pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=4)

    def test_boost_mismatch_5pl_follows_caption_not_sysname(
            self, novibet_racecard_boost_mismatch_5pl):
        # sysname says 2 places at 1/5; the caption says 5 places at 1/5.
        race = _parse(novibet_racecard_boost_mismatch_5pl,
                      venue="Galway", country="IRE")
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=5)

    def test_six_places_is_parsed_not_dropped(self, novibet_racecard_6pl):
        # arb_finder skips it later (Betfair stops at TOP_5); novibet.json
        # still records the true terms.
        race = _parse(novibet_racecard_6pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=6)

    def test_no_each_way_market_yields_none(self, novibet_racecard_no_eachway):
        race = _parse(novibet_racecard_no_eachway, venue="Musselburgh")
        assert race.each_way_terms is None
        assert len(race.runners) == 5  # win market is still there

    def test_each_way_pulled_near_off_yields_none(self, novibet_racecard_near_off):
        race = _parse(novibet_racecard_near_off)
        assert race.each_way_terms is None
        assert len(race.runners) == 15

    def test_unparseable_caption_yields_none(self, novibet_racecard_3pl):
        p = mutate(novibet_racecard_3pl)
        cat = next(c for c in p["marketCategories"] if "EACHWAY" in c["sysname"])
        cat["caption"] = "Enhanced Each Way Special"
        race = _parse(p)
        assert race.each_way_terms is None


class TestParseRacecard:
    def test_race_metadata(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        assert isinstance(race, NovibetRace)
        assert race.venue == "Wolverhampton"
        assert race.country == "GB"
        assert race.off_time == "2026-07-31T13:00:00+00:00"
        assert race.market_name == "Race Winner"
        assert race.scraped_at == SCRAPED

    def test_runner_prices(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        by_name = {r.name: r for r in race.runners}
        assert by_name["Marianne Mozart"].win_price == 15.0
        assert by_name["Marianne Mozart"].win_price_raw == "14/1"
        for r in race.runners:
            assert (r.win_price is None) == (r.win_price_raw is None)

    def test_non_runners_are_excluded(self, novibet_racecard_6pl):
        # 22 horses on the card, 4 NonRunner, 18 in the win market.
        race = _parse(novibet_racecard_6pl)
        assert len(race.runners) == 18
        names = {r.name for r in race.runners}
        for nr in ("Beagle Bay", "Cosi Bello", "Mirsky", "Rhoscolyn"):
            assert nr not in names

    def test_unavailable_runner_kept_but_price_nulled(self, novibet_racecard_3pl):
        p = mutate(novibet_racecard_3pl)
        win = next(c for c in p["marketCategories"]
                   if c["sysname"] == "HORSE_RACING_MAIN")
        item = win["items"][0]["betViews"][0]["betItems"][0]
        victim = item["caption"]
        item["isAvailable"] = False
        race = _parse(p, venue="Wolverhampton")
        got = next(r for r in race.runners if r.name == victim)
        assert got.win_price is None and got.win_price_raw is None

    def test_no_markets_yields_none(self, novibet_racecard_no_markets):
        assert _parse(novibet_racecard_no_markets, venue="Fairview",
                      country="SAF") is None

    def test_missing_or_malformed_payload_yields_none(self):
        assert _parse({}) is None
        assert _parse({"marketCategories": []}) is None
        assert _parse({"startDateTime": "2026-07-31T13:00:00+00:00",
                       "marketCategories": []}) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_racecard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.racecard'`

- [ ] **Step 3: Write `src/novibet_scraper/racecard.py`**

```python
"""Parse a horse-racing-race2 response into one NovibetRace.

Two things to know about this payload:

1. Each-way terms come from the caption of the EACHWAY market category, NOT
   its sysname. The sysname looks like <places>_<divisor> and usually is,
   but on Place Boost races it keeps the base terms while the caption
   advertises the boosted ones actually on offer (5 of 30 GB/IRE races on
   the capture day disagreed). There is no sysname fallback: a wrong
   fraction or place count misprices every runner in the race, always in
   the direction of phantom arbs.

2. The win market already excludes non-runners — `horses[]` carries the
   full card with horseStatus, the win market only the actual runners. We
   iterate the win market and additionally drop anything flagged
   NonRunner, so a change at either end cannot leak one through."""

from __future__ import annotations

import re

from .models import EachWayTerms, NovibetRace, NovibetRunner

WIN_CATEGORY = "HORSE_RACING_MAIN"
EACHWAY_PREFIX = "HORSE_RACING_RACE_WINNER_EACHWAY_"
MARKET_NAME = "Race Winner"

# "E/W 1/5 - 3 Places" and "Place Boost 1/5 - 4 Places" both match.
_TERMS_RE = re.compile(r"1\s*/\s*(\d+)\s*-\s*(\d+)\s*places?", re.IGNORECASE)


def parse_each_way_caption(caption: str) -> "EachWayTerms | None":
    """Extract terms from a market-category caption. None if unparseable."""
    if not isinstance(caption, str):
        return None
    m = _TERMS_RE.search(caption)
    if m is None:
        return None
    divisor = int(m.group(1))
    places = int(m.group(2))
    if divisor <= 0 or places <= 0:
        return None
    fraction = 1.0 / divisor
    if not (0.0 < fraction <= 1.0):
        return None
    return EachWayTerms(fraction=fraction, places=places)


def parse_racecard(
    payload: dict, scraped_at_utc: str, *, venue: str, country: str
) -> "NovibetRace | None":
    """Build a NovibetRace, or None when the payload carries no usable win
    market (race at/after the off, or a malformed response)."""
    if not isinstance(payload, dict):
        return None
    off_time = payload.get("startDateTime")
    if not (isinstance(off_time, str) and off_time):
        return None
    categories = payload.get("marketCategories")
    if not isinstance(categories, list) or not categories:
        return None

    non_runners = _non_runner_names(payload.get("horses"))
    runners = _parse_runners(_category(categories, WIN_CATEGORY), non_runners)
    if not runners:
        return None

    return NovibetRace(
        venue=venue,
        country=country,
        off_time=off_time,
        market_name=MARKET_NAME,
        scraped_at=scraped_at_utc,
        each_way_terms=_parse_eachway(categories),
        runners=runners,
    )


def _category(categories: list, sysname: str) -> "dict | None":
    for c in categories:
        if isinstance(c, dict) and c.get("sysname") == sysname:
            return c
    return None


def _parse_eachway(categories: list) -> "EachWayTerms | None":
    for c in categories:
        if not isinstance(c, dict):
            continue
        sysname = c.get("sysname")
        if isinstance(sysname, str) and sysname.startswith(EACHWAY_PREFIX):
            return parse_each_way_caption(c.get("caption"))
    return None


def _non_runner_names(horses: object) -> set:
    if not isinstance(horses, list):
        return set()
    out = set()
    for h in horses:
        if not isinstance(h, dict):
            continue
        name = h.get("horseName")
        if isinstance(name, str) and name and h.get("horseStatus") != "Runner":
            out.add(name)
    return out


def _bet_items(category: "dict | None") -> list:
    if not isinstance(category, dict):
        return []
    for item in category.get("items") or []:
        if not isinstance(item, dict):
            continue
        for view in item.get("betViews") or []:
            if isinstance(view, dict) and isinstance(view.get("betItems"), list):
                return view["betItems"]
    return []


def _parse_runners(category: "dict | None", non_runners: set) -> list[NovibetRunner]:
    out: list[NovibetRunner] = []
    for b in _bet_items(category):
        if not isinstance(b, dict):
            continue
        name = b.get("caption")
        if not (isinstance(name, str) and name) or name in non_runners:
            continue
        price = _to_float(b.get("price"))
        raw = b.get("oddsText")
        raw = raw if isinstance(raw, str) and raw else None
        if b.get("isAvailable") is not True or price is None or price <= 0.0 \
                or raw is None:
            price = None
            raw = None
        out.append(NovibetRunner(name=name, win_price=price, win_price_raw=raw))
    return out


def _to_float(v: object) -> "float | None":
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_novibet_racecard.py -v`
Expected: 19 passed.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: no failures.

- [ ] **Step 6: Commit**

```bash
git add src/novibet_scraper/racecard.py tests/test_novibet_racecard.py
git commit -m "feat(novibet): racecard parser, each-way terms from the caption

The EACHWAY category sysname disagrees with its caption on Place Boost
races (5 of 30 GB/IRE races on the capture day). The caption is the only
trustworthy source, so it is parsed with no sysname fallback: trusting the
sysname would inflate the place fraction and select the wrong Betfair TOP_N
lay, both biased toward reporting arbs that do not exist.

Non-runners are excluded twice over — the win market already omits them,
and anything flagged NonRunner in horses[] is dropped as well.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `output.py` + shared scrape validator + `validate.py`

**Files:**
- Create: `src/novibet_scraper/output.py`, `src/novibet_scraper/validation.py`, `src/novibet_scraper/validate.py`, `src/common/scrapevalidation.py`
- Modify: `src/paddypower_scraper/validation.py`, `src/sport888_scraper/validation.py`
- Test: `tests/test_novibet_output.py`, `tests/test_novibet_validation.py` (create)

**Interfaces:**
- Produces:
  - `novibet_scraper.output.write_novibet_json(out: NovibetOutput, path: Path | str) -> None`
  - `novibet_scraper.output.NOVIBET_RENAME: dict[str, str]`
  - `common.scrapevalidation.validate_bookie_scrape(text: str, *, required_race_strings: tuple[str, ...] = ()) -> list[str]`
  - `novibet_scraper.validation.validate_novibet_output(text: str) -> list[str]`
  - `novibet_scraper.validate.main(argv=None) -> int`
  - `paddypower_scraper.validation.validate_paddy_output` and
    `sport888_scraper.validation.validate_sport888_output` keep their exact
    current names, signatures and error strings.

- [ ] **Step 1: Write the failing tests**

`tests/test_novibet_output.py`:

```python
import json

from novibet_scraper.models import (
    EachWayTerms, NovibetOutput, NovibetRace, NovibetRunner,
)
from novibet_scraper.output import write_novibet_json
from novibet_scraper.validation import validate_novibet_output


def _out() -> NovibetOutput:
    return NovibetOutput(
        scraped_at="2026-07-31T12:00:00Z",
        race_count=1,
        races=[NovibetRace(
            venue="Wolverhampton", country="GB",
            off_time="2026-07-31T13:00:00+00:00", market_name="Race Winner",
            scraped_at="2026-07-31T12:00:00Z",
            each_way_terms=EachWayTerms(fraction=0.2, places=3),
            runners=[NovibetRunner("Marianne Mozart", 15.0, "14/1"),
                     NovibetRunner("Suspended", None, None)])],
    )


def test_writes_camel_case(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["scrapedAt"] == "2026-07-31T12:00:00Z"
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["offTime"] == "2026-07-31T13:00:00+00:00"
    assert race["marketName"] == "Race Winner"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    assert race["runners"][0] == {"name": "Marianne Mozart",
                                  "winPrice": 15.0, "winPriceRaw": "14/1"}
    assert race["runners"][1] == {"name": "Suspended",
                                  "winPrice": None, "winPriceRaw": None}


def test_written_output_validates(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(_out(), p)
    assert validate_novibet_output(p.read_text()) == []


def test_empty_output_validates(tmp_path):
    p = tmp_path / "novibet.json"
    write_novibet_json(NovibetOutput("2026-07-31T12:00:00Z", 0, []), p)
    assert validate_novibet_output(p.read_text()) == []
```

`tests/test_novibet_validation.py`:

```python
import json

from novibet_scraper.validation import validate_novibet_output

GOOD = {
    "scrapedAt": "2026-07-31T12:00:00Z",
    "raceCount": 1,
    "races": [{
        "venue": "Wolverhampton", "country": "GB",
        "offTime": "2026-07-31T13:00:00+00:00", "marketName": "Race Winner",
        "scrapedAt": "2026-07-31T12:00:00Z",
        "eachWayTerms": {"fraction": 0.2, "places": 3},
        "runners": [{"name": "Marianne Mozart",
                     "winPrice": 15.0, "winPriceRaw": "14/1"}],
    }],
}


def _errs(mutate=None):
    payload = json.loads(json.dumps(GOOD))
    if mutate:
        mutate(payload)
    return validate_novibet_output(json.dumps(payload))


def test_good_payload_has_no_errors():
    assert _errs() == []


def test_not_json():
    assert validate_novibet_output("not json")


def test_race_count_must_match():
    assert any("raceCount" in e for e in _errs(
        lambda p: p.update(raceCount=7)))


def test_off_time_must_carry_an_offset():
    assert any("offTime" in e for e in _errs(
        lambda p: p["races"][0].update(offTime="2026-07-31T13:00:00")))


def test_six_places_is_accepted():
    # Novibet runs 6-place boosts; novibet.json records them even though the
    # arb step cannot price them (Betfair stops at TOP_5).
    assert _errs(lambda p: p["races"][0]["eachWayTerms"].update(places=6)) == []


def test_zero_places_is_rejected():
    assert any("places" in e for e in _errs(
        lambda p: p["races"][0]["eachWayTerms"].update(places=0)))


def test_fraction_out_of_range_is_rejected():
    assert any("fraction" in e for e in _errs(
        lambda p: p["races"][0]["eachWayTerms"].update(fraction=1.5)))


def test_null_each_way_terms_is_allowed():
    assert _errs(lambda p: p["races"][0].update(eachWayTerms=None)) == []


def test_price_parity_is_enforced():
    assert any("parity" in e for e in _errs(
        lambda p: p["races"][0]["runners"][0].update(winPriceRaw=None)))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_novibet_output.py tests/test_novibet_validation.py -v`
Expected: FAIL — `ModuleNotFoundError` for `novibet_scraper.output`.

- [ ] **Step 3: Write `src/novibet_scraper/output.py`**

```python
"""Serialize NovibetOutput to novibet.json with camelCase keys, atomic
write. Delegates to common.jsonio.write_json."""

from __future__ import annotations

from pathlib import Path

from common.jsonio import write_json

from .models import NovibetOutput

NOVIBET_RENAME = {
    "each_way_terms": "eachWayTerms",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "off_time": "offTime",
    "market_name": "marketName",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_novibet_json(out: NovibetOutput, path: Path | str) -> None:
    write_json(out, NOVIBET_RENAME, path)
```

- [ ] **Step 4: Extract the shared validator core, then delegate all three**

The PaddyPower and 888 validators are the same logic twice; adding a third copy for Novibet was the plan's original instruction and has been **overruled by the human partner** in favour of extracting the shared core. Diffing them shows exactly two substantive differences: PaddyPower additionally requires a `raceUrl` string on each race, and its price-parity block is a cosmetic rewrite that emits byte-identical messages.

Create `src/common/scrapevalidation.py` holding the current body of `sport888_scraper/validation.py`, with these changes:

- module docstring describes a generic bookie scrape;
- the public function becomes
  `validate_bookie_scrape(text: str, *, required_race_strings: tuple[str, ...] = ()) -> list[str]`;
- inside the per-race loop, immediately **after** the `marketName` check and **before** the `scrapedAt` check, add:

```python
        for extra in required_race_strings:
            _require_str(race, extra, errors)
```

- `_require_str`, `_require_int` and `_EW_PLACES = range(1, 7)` move across unchanged.

Then reduce the three bookie modules to delegations, each keeping its current public name, signature and docstring intent:

```python
# src/paddypower_scraper/validation.py
from common.scrapevalidation import validate_bookie_scrape

def validate_paddy_output(text: str) -> list[str]:
    return validate_bookie_scrape(text, required_race_strings=("raceUrl",))
```

```python
# src/sport888_scraper/validation.py
from common.scrapevalidation import validate_bookie_scrape

def validate_sport888_output(text: str) -> list[str]:
    return validate_bookie_scrape(text)
```

```python
# src/novibet_scraper/validation.py
from common.scrapevalidation import validate_bookie_scrape

def validate_novibet_output(text: str) -> list[str]:
    return validate_bookie_scrape(text)
```

**The existing validator tests are the gate.** `tests/test_paddy_validation.py`, `tests/test_paddy_validate_cli.py` and `tests/test_sport888_validation.py` assert specific error strings and must pass **unchanged** — they are what proves the extraction preserved behaviour, including message wording and the order errors are appended. Do not edit them to fit the new code.

Ordering matters: `raceUrl` must be checked between `marketName` and `scrapedAt` so PaddyPower's error sequence is preserved.

- [ ] **Step 5: Write `src/novibet_scraper/validate.py`**

Copy `src/sport888_scraper/validate.py`, changing the import to `from .validation import validate_novibet_output`, the call site, and the usage string to `python -m novibet_scraper.validate <novibet.json>`.

- [ ] **Step 6: Run the new tests**

Run: `uv run pytest tests/test_novibet_output.py tests/test_novibet_validation.py -v`
Expected: 12 passed.

- [ ] **Step 7: Prove the extraction changed nothing for the other two bookies**

Run: `uv run pytest tests/test_paddy_validation.py tests/test_paddy_validate_cli.py tests/test_sport888_validation.py -v`
Expected: all pass, with **no edits to those test files**.

Then the whole suite: `uv run pytest -q` — no failures.

- [ ] **Step 8: Commit**

```bash
git add src/common/scrapevalidation.py src/novibet_scraper/output.py \
        src/novibet_scraper/validation.py src/novibet_scraper/validate.py \
        src/paddypower_scraper/validation.py src/sport888_scraper/validation.py \
        tests/test_novibet_output.py tests/test_novibet_validation.py
git commit -m "feat(novibet): novibet.json serializer + shared scrape validator

The PaddyPower and 888 scrape validators were the same logic twice; rather
than adding a third copy for Novibet, the common core moves to
common/scrapevalidation.py, parameterised by the extra race-level string
fields a bookie requires (PaddyPower alone requires raceUrl). All three
bookie modules keep their public names and error strings — the existing
PaddyPower and 888 validator tests pass unchanged, which is what proves the
extraction preserved behaviour.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: `browser.py`

**Files:**
- Create: `src/novibet_scraper/browser.py`
- Test: `tests/test_novibet_browser.py` (create)

**Interfaces:**
- Consumes: `novibet_scraper.api.{WARMUP_URL, USER_AGENT, LOCALE, TIMEZONE, API_HEADERS}`
- Produces: `novibet_scraper.browser.BrowserSession` (context manager, `fetch_json(url, timeout_ms=20_000) -> dict`), `novibet_scraper.browser.BrowserFetchError(url, reason)`

Start from `src/sport888_scraper/browser.py`. Two differences: the in-page `fetch()` must send `API_HEADERS` (888 sends only `accept`), and the constants come from Novibet's `api`.

This is a third near-identical copy of the session class, and that is a deliberate call: when the shared-validator extraction was approved (Task 9), extracting the browser layer as well was considered and declined, because it would rewrite the one component whose failure silently breaks live scraping across two working scrapers. The spec already records browser extraction as the next cleanup.

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the Novibet browser session — no network.

The live path is covered by the opt-in integration test in Task 13."""

from __future__ import annotations

import json

import pytest

from novibet_scraper import api
from novibet_scraper.browser import BrowserFetchError, BrowserSession


class _FakePage:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, js, args):
        self.calls.append((js, args))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _session_with(page) -> BrowserSession:
    s = BrowserSession()
    s._page = page
    return s


def test_fetch_json_parses_the_body():
    page = _FakePage(json.dumps({"days": []}))
    assert _session_with(page).fetch_json("https://x/y") == {"days": []}


def test_fetch_json_sends_the_gateway_headers():
    page = _FakePage(json.dumps({}))
    _session_with(page).fetch_json("https://x/y")
    _js, args = page.calls[0]
    url, headers, timeout = args
    assert url == "https://x/y"
    assert headers == api.API_HEADERS
    assert timeout == 20_000


def test_fetch_json_raises_on_invalid_json():
    page = _FakePage("<html>403</html>")
    with pytest.raises(BrowserFetchError) as e:
        _session_with(page).fetch_json("https://x/y")
    assert "invalid JSON" in e.value.reason


def test_fetch_json_wraps_evaluation_failure():
    page = _FakePage(RuntimeError("HTTP 403: blocked"))
    with pytest.raises(BrowserFetchError) as e:
        _session_with(page).fetch_json("https://x/y")
    assert "403" in e.value.reason


def test_fetch_json_before_enter_is_a_runtime_error():
    with pytest.raises(RuntimeError):
        BrowserSession().fetch_json("https://x/y")


def test_warmup_url_is_novibets_racing_page():
    assert api.WARMUP_URL.startswith("https://www.novibet.ie/")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_browser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novibet_scraper.browser'`

- [ ] **Step 3: Write `src/novibet_scraper/browser.py`**

```python
"""Playwright-driven browser session for Novibet feed calls.

Novibet sits behind Cloudflare: a bare request gets a 403 challenge page.
One BrowserSession per scraper run warms up on __enter__ (which clears the
challenge and seeds session cookies), then reuses the same context for every
fetch_json call. The x-gw-* gateway headers ride on each in-page fetch."""

from __future__ import annotations

import json
from types import TracebackType
from typing import Type

from playwright.sync_api import Playwright, sync_playwright

from .api import API_HEADERS, LOCALE, TIMEZONE, USER_AGENT, WARMUP_URL


class BrowserFetchError(Exception):
    """Raised when an in-page fetch returns non-2xx, fails to evaluate,
    or returns invalid JSON."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


_FETCH_JS = """
async ([url, headers, timeoutMs]) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(url, {
            method: 'GET',
            credentials: 'include',
            headers: headers,
            signal: controller.signal,
        });
        if (!r.ok) {
            const text = await r.text();
            throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 500));
        }
        return await r.text();
    } finally {
        clearTimeout(timer);
    }
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
        self._page.goto(WARMUP_URL, timeout=30_000)
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
            body = self._page.evaluate(_FETCH_JS, [url, API_HEADERS, timeout_ms])
        except Exception as e:
            raise BrowserFetchError(url, str(e)) from e
        if not isinstance(body, str):
            raise BrowserFetchError(
                url, f"unexpected response type: {type(body).__name__}")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise BrowserFetchError(url, f"invalid JSON: {e}") from e
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_novibet_browser.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/novibet_scraper/browser.py tests/test_novibet_browser.py
git commit -m "feat(novibet): headless-Chromium session with gateway headers

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: `cli.py` + `__main__.py`

**Files:**
- Create: `src/novibet_scraper/cli.py`, `src/novibet_scraper/__main__.py`
- Test: `tests/test_novibet_cli.py` (create)

**Interfaces:**
- Consumes: everything built in Tasks 4–10, plus `common.regions.parse_regions`, `common.timeutil.iso_utc`, `paddypower_scraper.filtering.{in_window, london_day_window}`
- Produces: `novibet_scraper.cli.main(argv=None, *, now_utc=None, make_session=..., out_path=Path("novibet.json")) -> int`

Exit codes match the other scrapers: 0 success/partial/empty, 1 index-fetch failure or every race failed, 2 bad args.

- [ ] **Step 1: Write the failing test**

```python
"""CLI orchestration for the Novibet scraper, with a stubbed session."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from novibet_scraper import api, cli
from novibet_scraper.browser import BrowserFetchError

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


class _StubSession:
    """Serves the committed fixtures by URL."""

    def __init__(self, racecards: dict, fail_index: bool = False):
        self.racecards = racecards
        self.fail_index = fail_index
        self.fetched: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch_json(self, url: str, timeout_ms: int = 20_000) -> dict:
        self.fetched.append(url)
        if url == api.OVERVIEW_URL:
            if self.fail_index:
                raise BrowserFetchError(url, "HTTP 403")
            return self.overview
        for bcid, payload in self.racecards.items():
            if f"/{bcid}" in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise BrowserFetchError(url, "HTTP 404")


def _run(session, tmp_path, argv=None):
    out = tmp_path / "novibet.json"
    rc = cli.main(argv if argv is not None else ["gb-ie"],
                  now_utc=NOW, make_session=lambda: session, out_path=out)
    return rc, out


def test_bad_region_exits_2(tmp_path):
    rc, _ = _run(_StubSession({}), tmp_path, ["atlantis"])
    assert rc == 2


def test_index_failure_exits_1(tmp_path, novibet_overview_payload):
    s = _StubSession({}, fail_index=True)
    s.overview = novibet_overview_payload
    rc, _ = _run(s, tmp_path)
    assert rc == 1


def test_writes_races_for_the_selected_region(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    rc, out = _run(s, tmp_path)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 1
    race = data["races"][0]
    assert race["venue"] == "Wolverhampton"
    assert race["country"] == "GB"
    assert race["eachWayTerms"] == {"fraction": 0.2, "places": 3}


def test_only_in_region_races_are_fetched(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    _run(s, tmp_path)
    # SAF/GER meetings exist in the fixture and must never be requested.
    # These are the four Fairview (SAF) betContextIds in novibet_overview.json.
    saf_ids = ("47381068", "47381069", "47381070", "47381071")
    assert not [u for u in s.fetched if any(f"/{i}" in u for i in saf_ids)]


def test_empty_day_writes_empty_output_and_exits_0(tmp_path):
    s = _StubSession({})
    s.overview = {"days": []}
    rc, out = _run(s, tmp_path)
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["raceCount"] == 0 and data["races"] == []


def test_all_races_failing_exits_1(tmp_path, novibet_overview_payload):
    s = _StubSession({})  # every racecard 404s
    s.overview = novibet_overview_payload
    rc, _ = _run(s, tmp_path)
    assert rc == 1


def test_partial_failure_still_writes_and_exits_0(
        tmp_path, novibet_overview_payload, novibet_racecard_3pl):
    s = _StubSession({"47383682": novibet_racecard_3pl})
    s.overview = novibet_overview_payload
    rc, out = _run(s, tmp_path)
    assert rc == 0
    assert json.loads(out.read_text())["raceCount"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'cli'`

- [ ] **Step 3: Write `src/novibet_scraper/cli.py`**

```python
"""Top-level orchestration for the Novibet scraper. Pure functions
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
from .models import NovibetOutput, NovibetRace
from .output import write_novibet_json
from .overview import parse_overview
from .racecard import parse_racecard
from .regions import countries_for_all


class SessionLike(Protocol):
    def fetch_json(self, url: str, timeout_ms: int = ...) -> dict: ...


def _default_session_factory() -> AbstractContextManager[BrowserSession]:
    return BrowserSession()


def main(
    argv: list[str] | None = None,
    *,
    now_utc: datetime | None = None,
    make_session: Callable[[], AbstractContextManager[SessionLike]] = _default_session_factory,
    out_path: Path | str = Path("novibet.json"),
) -> int:
    """Return exit code (0 = success/partial/empty, 1 = fetch error, 2 = bad args)."""
    argv = argv if argv is not None else sys.argv[1:]
    region_arg = argv[0] if argv else "gb-ie"

    try:
        wanted = countries_for_all(parse_regions(region_arg))
    except ValueError as e:
        print(f"novibet-scraper: {e}", file=sys.stderr)
        return 2

    now = now_utc or datetime.now(timezone.utc)
    window = london_day_window(now)
    out_path = Path(out_path)

    print(f"Fetching Novibet day index for regions={region_arg}...")

    with make_session() as session:
        try:
            index_payload = session.fetch_json(api.OVERVIEW_URL)
        except BrowserFetchError as e:
            print(f"novibet: day index fetch failed: {e.reason}", file=sys.stderr)
            return 1

        stubs = parse_overview(index_payload)
        in_region = [s for s in stubs if s.country in wanted]
        in_today = [s for s in in_region if in_window(s.start_time_utc, window)]

        if not in_today:
            _write(out_path, now, [])
            print(f"Wrote {out_path} (0 races, 0 skipped)")
            return 0

        in_today.sort(key=lambda s: s.start_time_utc)

        races: list[NovibetRace] = []
        attempted = 0
        skipped = 0
        for stub in in_today:
            attempted += 1
            url = api.racecard_url(stub.bet_context_id)
            scraped_at = iso_utc(datetime.now(timezone.utc))
            try:
                payload = session.fetch_json(url)
                race = parse_racecard(payload, scraped_at,
                                      venue=stub.venue, country=stub.country)
            except BrowserFetchError as e:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: {e.reason}", file=sys.stderr)
                skipped += 1
                continue
            except Exception as e:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: parse error: {e}", file=sys.stderr)
                skipped += 1
                continue
            if race is None:
                print(f"novibet: skipping race {stub.bet_context_id} "
                      f"{stub.venue}: no usable win market", file=sys.stderr)
                skipped += 1
                continue
            races.append(race)

        if attempted > 0 and not races:
            print("novibet: every attempted race failed", file=sys.stderr)
            return 1

        seen: set[tuple[str, str]] = set()
        deduped: list[NovibetRace] = []
        for r in races:
            key = (r.venue, r.off_time)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r.off_time)

        no_terms = 0
        for r in deduped:
            ew = r.each_way_terms
            if ew is None:
                no_terms += 1
                ew_str = "eachway=no"
            else:
                ew_str = f"eachway={ew.fraction:.2f} places={ew.places}"
            print(f"  {r.off_time[11:16]} {r.venue} → {len(r.runners)} runners, {ew_str}")

        meetings = len({r.venue for r in deduped})
        _write(out_path, now, deduped)
        print(f"Wrote {out_path} ({len(deduped)} races from {meetings} "
              f"meetings, {skipped} skipped, {no_terms} without each-way terms)")
        return 0


def _write(out_path: Path, now: datetime, races: list[NovibetRace]) -> None:
    write_novibet_json(
        NovibetOutput(scraped_at=iso_utc(now), race_count=len(races), races=races),
        out_path,
    )
```

- [ ] **Step 4: Write `src/novibet_scraper/__main__.py`**

```python
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_novibet_cli.py -v`
Expected: 7 passed.

Note on `test_writes_races_for_the_selected_region`: the fixture's day-1 (Aug 01) races fall outside `london_day_window(2026-07-31T12:00Z)` and are filtered out; of the Jul 31 GB/IRE races only `47383682` is stubbed, and the rest raise `HTTP 404` and are counted as skipped. That is the intended partial-failure path.

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: no failures.

- [ ] **Step 7: Commit**

```bash
git add src/novibet_scraper/cli.py src/novibet_scraper/__main__.py \
        tests/test_novibet_cli.py
git commit -m "feat(novibet): CLI orchestration (day index -> per-race fan-out)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — wiring

### Task 12: `arb_finder --source novibet`

**Files:**
- Modify: `src/arb_finder/bookies.py`, `src/arb_finder/cli.py`
- Test: `tests/test_novibet_arb.py` (create)

**Interfaces:**
- Consumes: `novibet_scraper.models.NovibetOutput`, `novibet_scraper.validation.validate_novibet_output`, `arb_finder.calculator.find_horses_by_name`
- Produces: `arb_finder.bookies.NOVIBET`, `SOURCES["novibet"]`

No calculator change is needed — `find_horses_by_name` already takes any bookie output with `.scraped_at` and `.races`.

- [ ] **Step 1: Write the failing test**

```python
"""arb_finder --source novibet: name+time join to Betfair -> novibethorses.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arb_finder import cli

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _write_inputs(tmp_path: Path, *, places: int = 3, fraction: float = 0.2):
    (tmp_path / "betfair.json").write_text(json.dumps({
        "scrapedAt": "2026-07-31T11:59:01Z",
        "raceCount": 1,
        "races": [{
            "raceId": "1.1", "venue": "Wolverhampton", "country": "GB",
            "offTime": "2026-07-31T14:00:00+01:00",
            "winMarketUrl": "https://www.betfair.com/exchange/plus/horse-racing/market/1.1",
            "marketName": "14:00 Wolverhampton",
            "marketScrapedAt": {"WIN": "2026-07-31T11:59:02Z",
                                "TOP_3": "2026-07-31T11:59:02Z",
                                "TOP_4": "2026-07-31T11:59:02Z"},
            "runners": [{"name": "Marianne Mozart",
                         "lay": {"WIN": 16.0, "TOP_3": 4.1, "TOP_4": 3.2},
                         "selectionId": 12345678}],
        }],
    }))
    (tmp_path / "novibet.json").write_text(json.dumps({
        "scrapedAt": "2026-07-31T11:59:07Z",
        "raceCount": 1,
        "races": [{
            "venue": "Wolverhampton", "country": "GB",
            # same instant as Betfair's +01:00 off time
            "offTime": "2026-07-31T13:00:00+00:00",
            "marketName": "Race Winner", "scrapedAt": "2026-07-31T11:59:07Z",
            "eachWayTerms": {"fraction": fraction, "places": places},
            "runners": [{"name": "Marianne Mozart",
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    }))


def _run(tmp_path: Path) -> int:
    return cli.main(["--source", "novibet",
                     str(tmp_path / "betfair.json"),
                     str(tmp_path / "novibet.json"),
                     str(tmp_path / "novibethorses.json")],
                    now=lambda: NOW)


def test_writes_novibethorses_with_a_novibet_leg(tmp_path: Path):
    _write_inputs(tmp_path)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horseCount"] == 1
    assert "novibetScrapedAt" in data
    horse = data["horses"][0]
    assert horse["novibet"]["winPrice"] == 15.0
    assert horse["novibet"]["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    # venue/country/ids come from the matched Betfair race
    assert horse["betfairWinMarketId"] == "1.1"
    assert horse["runner"]["selectionId"] == 12345678
    assert horse["betfair"]["placeMarket"] == "TOP_3"


def test_four_places_selects_top_4(tmp_path: Path):
    _write_inputs(tmp_path, places=4)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horses"][0]["betfair"]["placeMarket"] == "TOP_4"


def test_six_places_is_unpriceable_and_yields_no_horses(tmp_path: Path):
    # Betfair's to-be-placed markets stop at TOP_5.
    _write_inputs(tmp_path, places=6)
    assert _run(tmp_path) == 0
    data = json.loads((tmp_path / "novibethorses.json").read_text())
    assert data["horseCount"] == 0


def test_output_passes_the_horses_schema(tmp_path: Path):
    # The bookie-aware validator from the unification refactor is what lets
    # novibethorses.json be schema-checked at all.
    from arb_finder.bookies import NOVIBET
    from arb_finder.validation import validate_horses_output

    _write_inputs(tmp_path)
    assert _run(tmp_path) == 0
    text = (tmp_path / "novibethorses.json").read_text()
    assert validate_horses_output(text, bookie=NOVIBET) == []


def test_empty_output_passes_the_horses_schema(tmp_path: Path):
    from arb_finder.bookies import NOVIBET
    from arb_finder.validation import validate_horses_output

    _write_inputs(tmp_path, places=6)  # unpriceable → zero horses
    assert _run(tmp_path) == 0
    text = (tmp_path / "novibethorses.json").read_text()
    assert validate_horses_output(text, bookie=NOVIBET) == []


def test_missing_input_exits_2(tmp_path: Path):
    assert cli.main(["--source", "novibet",
                     str(tmp_path / "nope.json"),
                     str(tmp_path / "also-nope.json"),
                     str(tmp_path / "out.json")], now=lambda: NOW) == 2


def test_defaults_resolve_to_novibet_filenames(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No positional args → betfair.json + novibet.json → novibethorses.json.
    # Inputs are absent, so this exits 2 having looked for the right names.
    assert cli.main(["--source", "novibet"], now=lambda: NOW) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_novibet_arb.py -v`
Expected: FAIL — `unknown --source novibet`, so every test returns 1 instead of 0/2.

- [ ] **Step 3: Add the registry entry in `src/arb_finder/bookies.py`**

```python
NOVIBET = Bookie(
    key="novibet",
    leg_field="novibet",
    scraped_at_field="novibetScrapedAt",
    default_bookie_input="novibet.json",
    default_output="novibethorses.json",
)

BOOKIES: dict[str, Bookie] = {b.key: b for b in (PADDYPOWER, SPORT888, NOVIBET)}
```

- [ ] **Step 4: Add the source spec in `src/arb_finder/cli.py`**

Add the imports:

```python
from novibet_scraper.models import NovibetOutput
from novibet_scraper.validation import validate_novibet_output
from .bookies import Bookie, NOVIBET, PADDYPOWER, SPORT888
```

and the entry to `SOURCES`:

```python
    "novibet": SourceSpec(
        bookie=NOVIBET, label="Novibet",
        parse=lambda t: NovibetOutput.from_dict(json.loads(t)),
        validate=validate_novibet_output, join="name"),
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_novibet_arb.py -v`
Expected: 7 passed.

- [ ] **Step 6: Update `tests/test_bookies.py`**

`test_registry_is_keyed_by_cli_token` now expects `{"paddypower", "888", "novibet"}`. Add a `test_novibet_declares_its_json_names` mirroring the other two.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q`
Expected: no failures. `tests/test_arb_finder_golden_bytes.py` must still pass.

- [ ] **Step 8: Commit**

```bash
git add src/arb_finder tests/test_novibet_arb.py tests/test_bookies.py
git commit -m "feat(arb): --source novibet -> novibethorses.json

One registry entry and one SOURCES row; the name+time join and the models
are the ones the unification refactor already generalised.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Pipeline, site, docs, integration test

**Files:**
- Modify: `run.sh`, `publish.sh`, `.gitignore`, `index.html`, `README.md`
- Test: `tests/test_novibet_packaging.py` (extend), `tests/test_site.py` (extend), `tests/test_novibet_integration.py` (create)

**Interfaces:**
- Consumes: `novibet_scraper.cli.main`, `novibet_scraper.browser.BrowserSession`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_novibet_packaging.py`:

```python
def test_run_sh_invokes_novibet_stages():
    text = (ROOT / "run.sh").read_text()
    assert "python -m novibet_scraper" in text
    assert "python -m arb_finder --source novibet" in text


def test_run_sh_novibet_stages_are_non_fatal():
    # A Novibet outage must never abort run.sh and block the PaddyPower publish.
    text = (ROOT / "run.sh").read_text()
    stage_lines = [
        l for l in text.splitlines()
        if "novibet_scraper" in l or "--source novibet" in l
    ]
    assert len(stage_lines) == 2, f"expected 2 novibet stage lines, got {stage_lines}"
    for line in stage_lines:
        assert "||" in line, f"novibet stage must be non-fatal: {line!r}"


def test_gitignore_lists_novibet_outputs():
    text = (ROOT / ".gitignore").read_text()
    assert "novibet.json" in text
    assert "novibethorses.json" in text
```

Append to `tests/test_site.py`:

```python
def test_index_offers_novibet_source():
    html = INDEX.read_text()
    assert "novibethorses.json" in html, "index.html missing novibethorses.json source"
    assert "novibet" in html, "index.html missing novibet bookie leg"


def test_publish_script_copies_novibethorses():
    text = (ROOT / "publish.sh").read_text()
    assert "novibethorses.json" in text, \
        "publish.sh should copy novibethorses.json to the site"
```

Create `tests/test_novibet_integration.py`:

```python
"""Opt-in live test against the real Novibet feed.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration
Skipped by default — it needs network and a Chromium install."""

from __future__ import annotations

import os

import pytest

from novibet_scraper import api
from novibet_scraper.browser import BrowserSession
from novibet_scraper.overview import parse_overview
from novibet_scraper.racecard import parse_racecard

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="live network test; set RUN_INTEGRATION=1 to run",
)


@pytest.mark.integration
def test_live_index_and_one_racecard():
    with BrowserSession() as session:
        payload = session.fetch_json(api.OVERVIEW_URL)
        stubs = parse_overview(payload)
        assert stubs, "live day index returned no races"

        gb = [s for s in stubs if s.country in ("GB", "IRE")]
        if not gb:
            pytest.skip("no GB/IRE racing in the live index today")

        race = None
        for stub in gb:
            card = session.fetch_json(api.racecard_url(stub.bet_context_id))
            race = parse_racecard(card, "2026-01-01T00:00:00Z",
                                  venue=stub.venue, country=stub.country)
            if race is not None:
                break
        assert race is not None, "no GB/IRE race had a usable win market"
        assert race.runners
        if race.each_way_terms is not None:
            assert 0.0 < race.each_way_terms.fraction <= 1.0
            assert race.each_way_terms.places >= 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_novibet_packaging.py tests/test_site.py -v`
Expected: the five new assertions FAIL; the integration test is skipped.

- [ ] **Step 3: Add the `run.sh` stages**

Append after the 888 stages, and update the header comment to mention Novibet:

```bash
uv run python -m novibet_scraper "$REGIONS" || echo "run.sh: novibet scrape failed (exit $?); PaddyPower publish unaffected" >&2
uv run python -m arb_finder --source novibet || echo "run.sh: novibet arb failed (exit $?); PaddyPower publish unaffected" >&2
```

- [ ] **Step 4: Add the `publish.sh` copy**

After the `888horses.json` line:

```bash
# novibethorses.json is optional for the same reason.
[ -f novibethorses.json ] && cp novibethorses.json public/
```

Note: `publish.sh` runs under `set -e`. The existing `[ -f … ] && cp …` line is the last-but-one statement in its block and works today; keep the new line in the same style, immediately after it, so a missing file leaves a non-zero status only on a line that is not the script's last. If the added line ends up last before `ORIGIN_URL=`, that is fine — the assignment resets `$?`. Verify with Step 8's live run.

- [ ] **Step 5: Add the `.gitignore` entries**

Add `novibet.json` and `novibethorses.json` alongside the existing output entries.

- [ ] **Step 6: Add the `index.html` source**

Add the option:

```html
          <option value="novibet">Novibet</option>
```

and the `SOURCES` entry:

```js
      novibet:    { file: "novibethorses.json", leg: "novibet",   label: "NB" },
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest -q`
Expected: no failures.

- [ ] **Step 8: Verify the live pipeline end to end**

```bash
uv run python -m novibet_scraper gb-ie
uv run python -m novibet_scraper.validate novibet.json
uv run python -m arb_finder --source novibet
```

Expected: `novibet.json` holds today's GB/IRE races with each-way terms; `validate` prints `OK`; `novibethorses.json` is written with a `novibet` leg and a summary line reporting races matched and runners unmatched.

**Sanity-check the each-way terms against the site.** Open two or three of the scraped races on `novibet.ie` and confirm the terms in `novibet.json` match what the page advertises — especially any race showing a **Place Boost**. This is the one failure mode the unit tests cannot fully close, because it depends on Novibet's live caption format.

Also confirm the race count is plausible (the capture day had 49 GB/IRE races) and that `races matched` is a high fraction of them — a low match rate means venue-name drift against Betfair, which is the known matching risk in the spec.

- [ ] **Step 9: Update `README.md`**

- Add the Novibet stage to the pipeline description at the top (it is currently "a three-stage pipeline"; it is now Betfair → PaddyPower → arb → 888 ×2 → Novibet ×2).
- Add `uv run python -m novibet_scraper gb-ie` to the "Run a single stage directly" block.
- Add `uv run python -m novibet_scraper.validate novibet.json` to "Validating output".
- Extend the web-page paragraph: the source toggle now offers PaddyPower, 888sport and Novibet.
- Add `novibet_scraper/` to the Architecture tree.

- [ ] **Step 10: Commit**

```bash
git add run.sh publish.sh .gitignore index.html README.md \
        tests/test_novibet_packaging.py tests/test_site.py \
        tests/test_novibet_integration.py
git commit -m "build(novibet): wire stages into run.sh/publish.sh + site toggle

Both Novibet stages are non-fatal, matching the 888 guard: an outage must
never block the PaddyPower publish. novibethorses.json is published only
when present, and index.html gains a third source-toggle entry.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Done when

- `uv run pytest -q` is green, with `tests/test_arb_finder_golden_bytes.py` proving `horses.json` and `888horses.json` are byte-identical to before the refactor.
- `./run.sh gb-ie` produces `betfair.json`, `paddypower.json`, `horses.json`, `888sport.json`, `888horses.json`, `novibet.json`, `novibethorses.json`.
- `./publish.sh` ships all three bookie files and the page's source toggle switches between them.
- Novibet's each-way terms have been eyeballed against the live site on at least one Place Boost race.
