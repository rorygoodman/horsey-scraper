# Python Rewrite — Plan 3: Arb finder + Kotlin/Gradle removal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Kotlin arb finder to `src/arb_finder/`, then delete the entire Kotlin/Gradle toolchain and finish the cutover (run.sh, README, .gitignore), leaving a green pure-Python pipeline.

**Architecture:** The arb finder imports `ScrapeOutput`/`validate_scrape_output` from `betfair_scraper` and `PaddyOutput`/`validate_paddy_output` from `paddypower_scraper` (the payoff of the single project). Port calculator → validator → CLI, golden-test the output, then remove Kotlin and rewire the three-step `run.sh` to `uv run`.

**Tech Stack:** Python ≥3.11, pytest, stdlib `json`/`datetime`.

**Spec:** `docs/superpowers/specs/2026-05-26-python-rewrite-design.md`

**Behavioral oracle (deleted at the end of this plan):**
`src/main/kotlin/com/horsey/scraper/arb/{ArbModels,ArbCalculator,ArbSchemaValidator,ArbMain}.kt` and tests under `src/test/kotlin/com/horsey/scraper/arb/`.

**Prerequisites:** Plan 1 + Plan 2 complete (green `common`, `paddypower_scraper`, `betfair_scraper`).

---

## Task 1: `arb_finder/models.py` — arb dataclasses + serializer (TDD)

Oracle: `ArbModels.kt`. Output field order matches `arbs.json`: top-level `computedAt, betfairScrapedAt, paddypowerScrapedAt, arbCount, arbs`; arb `venue, country, offTime, marketName, betfairWinMarketId, runner, paddypower, betfair, margin`. `EachWayTerms` is reused from `paddypower_scraper.models`; `topNType` is a `MarketType` (serialized as `.name`).

**Files:**
- Create: `src/arb_finder/models.py`
- Test: `tests/test_arb_models.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_arb_models.py`:
```python
"""Tests for arb_finder.models serialization."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    Arb,
    ArbOutput,
    ArbRunner,
    BetfairLayLeg,
    PaddyPriceLeg,
    write_arbs_json,
)


def _sample() -> ArbOutput:
    return ArbOutput(
        computed_at="2026-05-25T17:06:08.398333Z",
        betfair_scraped_at="2026-05-25T17:05:56.890289Z",
        paddypower_scraped_at="2026-05-25T17:05:58.384555Z",
        arb_count=1,
        arbs=[
            Arb(
                venue="Ballinrobe",
                country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                market_name="18:05 Ballinrobe",
                betfair_win_market_id="1.258528220",
                runner=ArbRunner(name="Sony Bill", selection_id=66986352),
                paddypower=PaddyPriceLeg(
                    win_price=3.0, win_price_raw="2/1",
                    each_way_terms=EachWayTerms(fraction=0.2, places=2)),
                betfair=BetfairLayLeg(
                    win_lay=2.0, top_n_lay=1.4, top_n_type=MarketType.TOP_2),
                margin=0.25,
            )
        ],
    )


def test_serialize_shape(tmp_path: Path):
    target = tmp_path / "arbs.json"
    write_arbs_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert list(payload.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "arbCount", "arbs",
    ]
    arb = payload["arbs"][0]
    assert list(arb.keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "margin",
    ]
    assert arb["runner"] == {"name": "Sony Bill", "selectionId": 66986352}
    assert arb["paddypower"] == {
        "winPrice": 3.0, "winPriceRaw": "2/1",
        "eachWayTerms": {"fraction": 0.2, "places": 2}}
    assert arb["betfair"] == {"winLay": 2.0, "topNLay": 1.4, "topNType": "TOP_2"}


def test_empty_arbs(tmp_path: Path):
    out = ArbOutput("2026-05-25T17:06:08.398333Z", "2026-05-25T17:05:56.890289Z",
                    "2026-05-25T17:05:58.384555Z", 0, [])
    target = tmp_path / "arbs.json"
    write_arbs_json(out, target)
    assert json.loads(target.read_text())["arbs"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_arb_models.py -q`
Expected: FAIL — `ModuleNotFoundError: arb_finder.models`.

- [ ] **Step 3: Implement `src/arb_finder/models.py`**

```python
"""Dataclasses mirroring arbs.json + serializer. Port of ArbModels.kt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.jsonio import write_json
from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms


@dataclass(frozen=True)
class PaddyPriceLeg:
    win_price: float
    win_price_raw: str
    each_way_terms: EachWayTerms


@dataclass(frozen=True)
class BetfairLayLeg:
    win_lay: float
    top_n_lay: float
    top_n_type: MarketType


@dataclass(frozen=True)
class ArbRunner:
    name: str
    selection_id: int


@dataclass(frozen=True)
class Arb:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: ArbRunner
    paddypower: PaddyPriceLeg
    betfair: BetfairLayLeg
    margin: float


@dataclass(frozen=True)
class ArbOutput:
    computed_at: str
    betfair_scraped_at: str
    paddypower_scraped_at: str
    arb_count: int
    arbs: list[Arb]


ARB_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
    "paddypower_scraped_at": "paddypowerScrapedAt",
    "arb_count": "arbCount",
    "off_time": "offTime",
    "market_name": "marketName",
    "betfair_win_market_id": "betfairWinMarketId",
    "selection_id": "selectionId",
    "win_price": "winPrice",
    "win_price_raw": "winPriceRaw",
    "each_way_terms": "eachWayTerms",
    "win_lay": "winLay",
    "top_n_lay": "topNLay",
    "top_n_type": "topNType",
}


def write_arbs_json(out: ArbOutput, path: Path | str) -> None:
    write_json(out, ARB_RENAME, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_arb_models.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/arb_finder/models.py tests/test_arb_models.py
git commit -m "arb_finder.models: arb dataclasses + serializer"
```

---

## Task 2: `arb_finder/calculator.py` — margin formula + arb join (TDD)

Oracle: `ArbCalculator.kt`; cases from `EachWayArbMarginTest.kt` + `FindArbsTest.kt`.

**Files:**
- Create: `src/arb_finder/calculator.py`
- Test: `tests/test_calculator.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_calculator.py`:
```python
"""Tests for arb_finder.calculator."""

from __future__ import annotations

import pytest

from common.markettype import MarketType
from betfair_scraper.models import RaceOdds, RunnerOdds, ScrapeOutput
from paddypower_scraper.models import (
    EachWayTerms,
    PaddyOutput,
    PaddyRace,
    PaddyRunner,
)
from arb_finder.calculator import each_way_arb_margin, find_arbs


class TestMargin:
    def test_known_value(self):
        # p=3, f=0.2, bw=2.0, bp=1.4:
        # lw = 3/4 = 0.75; lp = (1 + 2*0.2)/2.8 = 1.4/2.8 = 0.5; margin = 0.25
        assert each_way_arb_margin(3.0, 0.2, 2.0, 1.4) == pytest.approx(0.25)

    def test_no_arb_negative(self):
        assert each_way_arb_margin(2.0, 0.2, 4.0, 3.0) < 0


def _betfair(win_lay, top_lay) -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-05-25T17:05:56.890289Z",
        race_count=1,
        races=[RaceOdds(
            race_id="1.1", venue="Ascot", country="GB",
            off_time="2026-05-25T18:00:00+01:00", win_market_url="u",
            market_name="18:00 Ascot",
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z",
                               MarketType.TOP_2: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds(
                name="A", lay={MarketType.WIN: win_lay, MarketType.TOP_2: top_lay},
                selection_id=1)],
        )],
    )


def _paddy() -> PaddyOutput:
    return PaddyOutput(
        scraped_at="2026-05-25T17:05:58.384555Z",
        race_count=1,
        races=[PaddyRace(
            venue="Ascot", country="GB", off_time="2026-05-25T18:00:00+01:00",
            market_name="18:00 Ascot", race_url="r",
            scraped_at="2026-05-25T17:05:58.384555Z",
            betfair_win_market_id="1.1",
            each_way_terms=EachWayTerms(fraction=0.2, places=2),
            runners=[PaddyRunner("A", 1, 3.0, "2/1")],
        )],
    )


class TestFindArbs:
    def test_positive_margin_emitted(self):
        arbs = find_arbs(_betfair(2.0, 1.4), _paddy())
        assert len(arbs) == 1
        assert arbs[0].runner.selection_id == 1
        assert arbs[0].betfair.top_n_type is MarketType.TOP_2
        assert arbs[0].margin == pytest.approx(0.25)

    def test_non_positive_margin_skipped(self):
        assert find_arbs(_betfair(4.0, 3.0), _paddy()) == []

    def test_skip_when_topn_market_absent(self):
        bf = _betfair(2.0, 1.4)
        # drop TOP_2 from the betfair race entirely
        race = bf.races[0]
        bf.races[0] = RaceOdds(
            race_id=race.race_id, venue=race.venue, country=race.country,
            off_time=race.off_time, win_market_url=race.win_market_url,
            market_name=race.market_name,
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds("A", {MarketType.WIN: 2.0}, 1)])
        assert find_arbs(bf, _paddy()) == []

    def test_sorted_by_margin_desc(self):
        # two runners, different margins
        bf = ScrapeOutput(
            "2026-05-25T17:05:56Z", 1,
            [RaceOdds("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u",
                      "18:00 Ascot",
                      {MarketType.WIN: "2026-05-25T17:05:58Z",
                       MarketType.TOP_2: "2026-05-25T17:05:58Z"},
                      [RunnerOdds("A", {MarketType.WIN: 2.0, MarketType.TOP_2: 1.4}, 1),
                       RunnerOdds("B", {MarketType.WIN: 2.0, MarketType.TOP_2: 1.2}, 2)])])
        paddy = PaddyOutput(
            "2026-05-25T17:05:58Z", 1,
            [PaddyRace("Ascot", "GB", "2026-05-25T18:00:00+01:00", "18:00 Ascot",
                       "r", "2026-05-25T17:05:58Z", "1.1",
                       EachWayTerms(0.2, 2),
                       [PaddyRunner("A", 1, 3.0, "2/1"),
                        PaddyRunner("B", 2, 3.0, "2/1")])])
        arbs = find_arbs(bf, paddy)
        assert [a.runner.selection_id for a in arbs] == [2, 1]  # B (1.2 lay) > A
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_calculator.py -q`
Expected: FAIL — `ModuleNotFoundError: arb_finder.calculator`.

- [ ] **Step 3: Implement `src/arb_finder/calculator.py`**

```python
"""Each-way arbitrage margin + the join that finds opportunities.
Port of ArbCalculator.kt."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places
from betfair_scraper.models import ScrapeOutput
from paddypower_scraper.models import PaddyOutput
from .models import Arb, ArbRunner, BetfairLayLeg, PaddyPriceLeg


def each_way_arb_margin(p: float, f: float, bw: float, bp: float) -> float:
    """Guaranteed profit per £1 PaddyPower each-way stake.

      L_w    = p / (2·bw)
      L_p    = (1 + (p−1)·f) / (2·bp)
      margin = L_w + L_p − 1"""
    lw = p / (2.0 * bw)
    lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0


def find_arbs(betfair: ScrapeOutput, paddy: PaddyOutput) -> list[Arb]:
    """Positive-margin each-way arbs, sorted by margin descending."""
    betfair_by_id = {r.race_id: r for r in betfair.races}
    out: list[Arb] = []

    for pr in paddy.races:
        win_market_id = pr.betfair_win_market_id
        if win_market_id is None:
            continue
        br = betfair_by_id.get(win_market_id)
        if br is None:
            continue
        ew = pr.each_way_terms
        if ew is None:
            continue
        top_n_type = top_n_from_places(ew.places)
        if top_n_type is None or top_n_type not in br.market_scraped_at:
            continue

        bf_by_sel = {r.selection_id: r for r in br.runners if r.selection_id is not None}

        for prun in pr.runners:
            sel = prun.selection_id
            if sel is None:
                continue
            brun = bf_by_sel.get(sel)
            if brun is None:
                continue
            pp_price = prun.win_price
            pp_raw = prun.win_price_raw
            if pp_price is None or pp_raw is None:
                continue
            win_lay = brun.lay.get(MarketType.WIN)
            top_n_lay = brun.lay.get(top_n_type)
            if win_lay is None or top_n_lay is None:
                continue

            margin = each_way_arb_margin(p=pp_price, f=ew.fraction, bw=win_lay, bp=top_n_lay)
            if margin <= 0.0:
                continue

            out.append(Arb(
                venue=pr.venue,
                country=pr.country,
                off_time=pr.off_time,
                market_name=pr.market_name,
                betfair_win_market_id=win_market_id,
                runner=ArbRunner(name=prun.name, selection_id=sel),
                paddypower=PaddyPriceLeg(
                    win_price=pp_price, win_price_raw=pp_raw, each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, top_n_lay=top_n_lay, top_n_type=top_n_type),
                margin=margin,
            ))

    out.sort(key=lambda a: a.margin, reverse=True)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_calculator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/arb_finder/calculator.py tests/test_calculator.py
git commit -m "arb_finder.calculator: each-way margin + arb join"
```

---

## Task 3: `arb_finder/validation.py` — arbs.json schema validator (TDD)

Oracle: `ArbSchemaValidator.kt`; cases from `ArbSchemaValidatorTest.kt`. Note: each-way `places` range here is **2..5** (tighter than the PaddyPower validator's 1..6).

**Files:**
- Create: `src/arb_finder/validation.py`
- Test: `tests/test_arb_validation.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_arb_validation.py`:
```python
"""Tests for arb_finder.validation."""

from __future__ import annotations

import json

from arb_finder.validation import validate_arbs_output


def _valid() -> dict:
    return {
        "computedAt": "2026-05-25T17:06:08.398333Z",
        "betfairScrapedAt": "2026-05-25T17:05:56.890289Z",
        "paddypowerScrapedAt": "2026-05-25T17:05:58.384555Z",
        "arbCount": 1,
        "arbs": [{
            "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "marketName": "18:00 Ascot",
            "betfairWinMarketId": "1.1",
            "runner": {"name": "A", "selectionId": 1},
            "paddypower": {"winPrice": 3.0, "winPriceRaw": "2/1",
                           "eachWayTerms": {"fraction": 0.2, "places": 2}},
            "betfair": {"winLay": 2.0, "topNLay": 1.4, "topNType": "TOP_2"},
            "margin": 0.25,
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_arbs_output(json.dumps(p))


def test_valid():
    assert _v(_valid()) == []


def test_empty_arbs_valid():
    p = {"computedAt": "2026-05-25T17:06:08Z",
         "betfairScrapedAt": "2026-05-25T17:05:56Z",
         "paddypowerScrapedAt": "2026-05-25T17:05:58Z",
         "arbCount": 0, "arbs": []}
    assert _v(p) == []


def test_arb_count_mismatch():
    p = _valid(); p["arbCount"] = 5
    assert any("arbCount" in e for e in _v(p))


def test_margin_must_be_positive():
    p = _valid(); p["arbs"][0]["margin"] = 0
    assert any("margin must be > 0" in e for e in _v(p))


def test_bad_topn_type():
    p = _valid(); p["arbs"][0]["betfair"]["topNType"] = "TOP_9"
    assert any("topNType" in e for e in _v(p))


def test_eachway_places_out_of_range():
    p = _valid(); p["arbs"][0]["paddypower"]["eachWayTerms"]["places"] = 6
    assert any("places must be in" in e for e in _v(p))


def test_missing_runner_selection_id():
    p = _valid(); del p["arbs"][0]["runner"]["selectionId"]
    assert any("selectionId" in e for e in _v(p))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_arb_validation.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/arb_finder/validation.py`**

```python
"""Validate an arbs.json payload string. Port of ArbSchemaValidator.kt."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(2, 6)  # 2..5 inclusive
_ALLOWED_TOP_N = {"TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_arbs_output(text: str) -> list[str]:
    errors: list[str] = []
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        return [f"not valid JSON object: {e}"]

    for key in ("computedAt", "betfairScrapedAt", "paddypowerScrapedAt"):
        _require_str(root, key, errors,
                     lambda v, k=key: None if is_iso_utc(v)
                     else errors.append(f"{k} is not ISO-8601 UTC instant: '{v}'"))
    arb_count = _require_int(root, "arbCount", errors)
    arbs = root.get("arbs")
    if not isinstance(arbs, list):
        errors.append("arbs: missing or not array")
        return errors
    if arb_count is not None and arb_count != len(arbs):
        errors.append(f"arbCount ({arb_count}) != arbs.length ({len(arbs)})")

    for i, arb in enumerate(arbs):
        ctx = f"arbs[{i}]"
        if not isinstance(arb, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(arb, "venue", errors)
        _require_str(arb, "country", errors)
        _require_str(arb, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(arb, "marketName", errors)
        _require_str(arb, "betfairWinMarketId", errors)

        margin = arb.get("margin")
        if not isinstance(margin, (int, float)) or isinstance(margin, bool):
            errors.append(f"{ctx}.margin: missing or not a number")
        elif margin <= 0.0:
            errors.append(f"{ctx}.margin must be > 0, got {margin}")

        runner = arb.get("runner")
        if not isinstance(runner, dict):
            errors.append(f"{ctx}.runner: missing or not an object")
        else:
            _require_str(runner, "name", errors)
            sel = runner.get("selectionId")
            if not isinstance(sel, (int, float)) or isinstance(sel, bool):
                errors.append(f"{ctx}.runner.selectionId: missing or not a number")

        _validate_paddy_leg(arb.get("paddypower"), f"{ctx}.paddypower", errors)
        _validate_betfair_leg(arb.get("betfair"), f"{ctx}.betfair", errors)
    return errors


def _validate_paddy_leg(el, ctx: str, errors: list[str]) -> None:
    if not isinstance(el, dict):
        errors.append(f"{ctx}: missing or not an object")
        return
    wp = el.get("winPrice")
    if not isinstance(wp, (int, float)) or isinstance(wp, bool):
        errors.append(f"{ctx}.winPrice: missing or not a number")
    _require_str(el, "winPriceRaw", errors)
    ew = el.get("eachWayTerms")
    if not isinstance(ew, dict):
        errors.append(f"{ctx}.eachWayTerms: missing or not an object")
        return
    frac = ew.get("fraction")
    if not isinstance(frac, (int, float)) or isinstance(frac, bool) \
            or not (0.0 < float(frac) <= 1.0):
        errors.append(f"{ctx}.eachWayTerms.fraction must be in (0,1], got {frac}")
    places = ew.get("places")
    if not isinstance(places, int) or isinstance(places, bool) or places not in _EW_PLACES:
        errors.append(f"{ctx}.eachWayTerms.places must be in {_EW_PLACES}, got {places}")


def _validate_betfair_leg(el, ctx: str, errors: list[str]) -> None:
    if not isinstance(el, dict):
        errors.append(f"{ctx}: missing or not an object")
        return
    for key in ("winLay", "topNLay"):
        v = el.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errors.append(f"{ctx}.{key}: missing or not a number")
    top_n = el.get("topNType")
    if not isinstance(top_n, str):
        errors.append(f"{ctx}.topNType: missing or not a string")
    elif top_n not in _ALLOWED_TOP_N:
        errors.append(f"{ctx}.topNType: '{top_n}' not in {_ALLOWED_TOP_N}")


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

Run: `uv run pytest tests/test_arb_validation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/arb_finder/validation.py tests/test_arb_validation.py
git commit -m "arb_finder.validation: arbs.json schema validator"
```

---

## Task 4: `arb_finder/cli.py` + `__main__.py` + `validate.py` (TDD)

Oracle: `ArbMain.kt` / `ArbValidateMain.kt`. Reads + validates both inputs, deserializes, computes, writes `arbs.json`.

**Files:**
- Create: `src/arb_finder/cli.py`
- Create: `src/arb_finder/__main__.py`
- Create: `src/arb_finder/validate.py`
- Test: `tests/test_arb_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_arb_cli.py`:
```python
"""Tests for the arb finder CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arb_finder.cli import main, parse_arb_cli_args


class TestParseArgs:
    def test_defaults(self):
        assert parse_arb_cli_args([]) == ("betfair.json", "paddypower.json", "arbs.json")

    def test_explicit(self):
        assert parse_arb_cli_args(["a", "b", "c"]) == ("a", "b", "c")

    def test_bad_arity(self):
        with pytest.raises(ValueError):
            parse_arb_cli_args(["only-one"])


def _write_betfair(path: Path):
    path.write_text(json.dumps({
        "scrapedAt": "2026-05-25T17:05:56.890289Z", "raceCount": 1,
        "races": [{
            "raceId": "1.1", "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "winMarketUrl": "u",
            "marketName": "18:00 Ascot",
            "marketScrapedAt": {"WIN": "2026-05-25T17:05:58Z",
                                "TOP_2": "2026-05-25T17:05:58Z"},
            "runners": [{"name": "A", "lay": {"WIN": 2.0, "TOP_2": 1.4},
                         "selectionId": 1}],
        }],
    }))


def _write_paddy(path: Path):
    path.write_text(json.dumps({
        "scrapedAt": "2026-05-25T17:05:58.384555Z", "raceCount": 1,
        "races": [{
            "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "marketName": "18:00 Ascot",
            "raceUrl": "r", "scrapedAt": "2026-05-25T17:05:58.384555Z",
            "betfairWinMarketId": "1.1",
            "eachWayTerms": {"fraction": 0.2, "places": 2},
            "runners": [{"name": "A", "selectionId": 1,
                         "winPrice": 3.0, "winPriceRaw": "2/1"}],
        }],
    }))


def test_happy_path_writes_arbs(tmp_path: Path):
    bf = tmp_path / "betfair.json"; _write_betfair(bf)
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    out = tmp_path / "arbs.json"
    rc = main([str(bf), str(pp), str(out)],
              now=lambda: datetime(2026, 5, 25, 17, 6, 8, tzinfo=timezone.utc))
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["arbCount"] == 1
    assert payload["arbs"][0]["runner"]["selectionId"] == 1
    assert payload["betfairScrapedAt"] == "2026-05-25T17:05:56.890289Z"


def test_missing_input_exits_2(tmp_path: Path):
    assert main([str(tmp_path / "nope.json"), str(tmp_path / "nope2.json"),
                 str(tmp_path / "arbs.json")]) == 2


def test_invalid_betfair_exits_2(tmp_path: Path):
    bf = tmp_path / "betfair.json"; bf.write_text('{"scrapedAt":"nope","raceCount":0,"races":[]}')
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    assert main([str(bf), str(pp), str(tmp_path / "arbs.json")]) == 2


def test_bad_arity_exits_1(tmp_path: Path):
    assert main(["only-one"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_arb_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: arb_finder.cli`.

- [ ] **Step 3: Implement `src/arb_finder/cli.py`**

```python
"""Arb finder entry point. Port of ArbMain.kt.
Reads + validates betfair.json and paddypower.json, computes arbs,
writes arbs.json. Exit 0 ok (even zero arbs), 1 bad usage, 2 input error."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from betfair_scraper.models import ScrapeOutput
from betfair_scraper.validation import validate_scrape_output
from common.timeutil import iso_utc
from paddypower_scraper.models import PaddyOutput
from paddypower_scraper.validation import validate_paddy_output
from .calculator import find_arbs
from .models import ArbOutput, write_arbs_json


def parse_arb_cli_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", "paddypower.json", "arbs.json")
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    raise ValueError(
        "usage: arb-finder                                          # all defaults\n"
        "       arb-finder <betfair-in> <paddypower-in> <arbs-out>  # all explicit"
    )


def main(argv=None, *, now=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        betfair_in, paddy_in, out_path = parse_arb_cli_args(argv)
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

    import json
    betfair = ScrapeOutput.from_dict(json.loads(betfair_text))
    paddy = PaddyOutput.from_dict(json.loads(paddy_text))

    computed_at = iso_utc((now or (lambda: datetime.now(timezone.utc)))())
    arbs = find_arbs(betfair, paddy)
    output = ArbOutput(
        computed_at=computed_at,
        betfair_scraped_at=betfair.scraped_at,
        paddypower_scraped_at=paddy.scraped_at,
        arb_count=len(arbs),
        arbs=arbs,
    )
    write_arbs_json(output, out_path)
    print(f"Wrote {out_path} ({len(arbs)} arbs from {len(betfair.races)} BF races "
          f"and {len(paddy.races)} PP races)")
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

- [ ] **Step 4: Create `src/arb_finder/__main__.py`**

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 5: Create `src/arb_finder/validate.py`**

```python
"""Validate an arbs.json file.
Usage: python -m arb_finder.validate [arbs.json]
Exit 0 = valid, 1 = errors, 2 = file error."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_arbs_output


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("arbs.json")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    errors = validate_arbs_output(path.read_text())
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

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_arb_cli.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/arb_finder/cli.py src/arb_finder/__main__.py src/arb_finder/validate.py tests/test_arb_cli.py
git commit -m "arb_finder: CLI orchestration + __main__ + validate entry"
```

---

## Task 5: Golden arbs round-trip + validator self-acceptance (TDD)

**Files:**
- Test: `tests/test_arb_golden.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_arb_golden.py`:
```python
"""The arb writer's output must pass the arb validator (in-process gate)."""

from __future__ import annotations

from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    Arb, ArbOutput, ArbRunner, BetfairLayLeg, PaddyPriceLeg, write_arbs_json,
)
from arb_finder.validation import validate_arbs_output


def test_written_arbs_validate(tmp_path: Path):
    out = ArbOutput(
        computed_at="2026-05-25T17:06:08.398333Z",
        betfair_scraped_at="2026-05-25T17:05:56.890289Z",
        paddypower_scraped_at="2026-05-25T17:05:58.384555Z",
        arb_count=1,
        arbs=[Arb(
            venue="Ascot", country="GB", off_time="2026-05-25T18:00:00+01:00",
            market_name="18:00 Ascot", betfair_win_market_id="1.1",
            runner=ArbRunner("A", 1),
            paddypower=PaddyPriceLeg(3.0, "2/1", EachWayTerms(0.2, 2)),
            betfair=BetfairLayLeg(2.0, 1.4, MarketType.TOP_2),
            margin=0.25)],
    )
    target = tmp_path / "arbs.json"
    write_arbs_json(out, target)
    assert validate_arbs_output(target.read_text()) == []


def test_empty_arbs_validate(tmp_path: Path):
    out = ArbOutput("2026-05-25T17:06:08Z", "2026-05-25T17:05:56Z",
                    "2026-05-25T17:05:58Z", 0, [])
    target = tmp_path / "arbs.json"
    write_arbs_json(out, target)
    assert validate_arbs_output(target.read_text()) == []
```

- [ ] **Step 2: Run tests to verify they pass (after implementing nothing new)**

Run: `uv run pytest tests/test_arb_golden.py -q`
Expected: PASS (both `write_arbs_json` and `validate_arbs_output` already exist). If `places` range mismatches (e.g. validator rejects places=2), reconcile `_EW_PLACES` in `arb_finder/validation.py`.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — `common` + PaddyPower + Betfair + arb (integration skipped).

- [ ] **Step 4: Commit**

```bash
git add tests/test_arb_golden.py
git commit -m "arb_finder: golden validator-accepts-output test"
```

---

## Task 6: Rewrite `run.sh` for the pure-Python pipeline

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh` contents**

```bash
#!/usr/bin/env bash
# Single positional arg: regions (default `gb-ie`; valid: gb-ie,us).
# Examples:
#   ./run.sh               # GB+IE
#   ./run.sh us            # US only
#   ./run.sh gb-ie,us      # both
#
# Pipeline: Betfair scrape → PaddyPower scrape → arb finder.
# A scrape failure exits non-zero before the arb step is reached.
set -euo pipefail
REGIONS="${1:-gb-ie}"
uv run python -m betfair_scraper "$REGIONS"
uv run python -m paddypower_scraper "$REGIONS"
exec uv run python -m arb_finder
```

- [ ] **Step 2: Verify the entry points import**

Run: `uv run python -c "import betfair_scraper.__main__" 2>&1 | head -1` — Expected: it executes `main()` (will try to load credentials; an `Error:` line + exit code is fine — it proves the module wires up). Safer dry check:
Run: `uv run python -c "import betfair_scraper.cli, paddypower_scraper.cli, arb_finder.cli; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "run.sh: pure-Python pipeline (3 × uv run)"
```

---

## Task 7: Rewrite `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` contents**

```markdown
# Horsey Scraper

A three-stage pipeline that finds each-way arbitrage between PaddyPower
win/place prices and Betfair Exchange lay prices for today's UK + Irish
horse racing:

1. **Betfair scrape** → `betfair.json` (multi-market lay prices via the
   Betfair Exchange REST API).
2. **PaddyPower scrape** → `paddypower.json` (win prices + each-way terms
   via a headless-Chromium fetch of PaddyPower's API).
3. **Arb finder** → `arbs.json` (positive-margin each-way arbs).

Pure Python. One `uv` project.

## Prerequisites

- Python ≥ 3.11 and [uv](https://github.com/astral-sh/uv).
- A Betfair account with **2FA disabled** (interactive login fails with
  `LOGIN_RESTRICTED` on 2FA-enabled accounts) and a live developer **app key**.

## One-time setup

```
brew install uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                              # creates .venv, installs deps
uv run playwright install chromium   # ~150MB; needed by the PaddyPower stage
```

## Credentials

Create `~/.horsey-scraper/credentials.json`:

```json
{
  "username": "your-betfair-username",
  "password": "your-betfair-password",
  "appKey": "your-app-key"
}
```

Recommended: `chmod 600 ~/.horsey-scraper/credentials.json`. The Betfair
stage warns to stderr if the file is readable by group/others.

## Usage

```
./run.sh               # GB + IE (default)
./run.sh us            # US only
./run.sh gb-ie,us      # both
```

Outputs are written to `./betfair.json`, `./paddypower.json`, `./arbs.json`.
A non-zero exit at any stage halts the pipeline before the arb step.

Run a single stage directly:

```
uv run python -m betfair_scraper gb-ie
uv run python -m paddypower_scraper gb-ie
uv run python -m arb_finder
```

## Validating output

```
uv run python -m betfair_scraper.validate betfair.json
uv run python -m paddypower_scraper.validate paddypower.json
uv run python -m arb_finder.validate arbs.json
```

## Tests

```
uv run pytest                                  # unit suite
RUN_INTEGRATION=1 uv run pytest -m integration # live network/browser (opt-in)
```

## Architecture

```
src/
  common/             shared: regions, market types, ISO validation,
                      time conversion, JSON serializer
  betfair_scraper/    Betfair Exchange API scraper → betfair.json
  paddypower_scraper/ headless-Chromium PaddyPower scraper → paddypower.json
  arb_finder/         joins both files → arbs.json
```

Design docs live under `docs/superpowers/specs/`, implementation plans
under `docs/superpowers/plans/`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "README: rewrite for pure-Python pipeline"
```

---

## Task 8: Clean up `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Replace `.gitignore` contents**

```gitignore
# Python
.venv/
.pytest_cache/
__pycache__/
**/__pycache__/
*.pyc

# IDE
.idea/
*.iml

# OS
.DS_Store
Thumbs.db

# Local scraper output
scraper.log
betfair.json
paddypower.json
arbs.json
debug-page.html

# Credentials — never commit. Real file lives at ~/.horsey-scraper/credentials.json.
credentials.json
*.env
```

- [ ] **Step 2: Verify no now-untracked build noise reappears**

Run: `git status --porcelain | grep -vE '^\?\? (docs/|$)' | head`
Expected: only intended changes (the `.gitignore` edit). The output JSON files stay ignored.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m ".gitignore: drop Gradle/Kotlin, generalize Python to repo root"
```

---

## Task 9: Delete the Kotlin / Gradle toolchain and finalize

**Files:**
- Delete: `src/main/`, `src/test/`, `build.gradle.kts`, `settings.gradle.kts`, `gradlew`, `gradlew.bat`, `gradle/`
- Delete (untracked dirs if present): `.gradle/`, `build/`

- [ ] **Step 1: Remove tracked Kotlin + Gradle files**

```bash
git rm -r src/main src/test build.gradle.kts settings.gradle.kts gradlew gradlew.bat gradle
```

> After this, `src/` contains only the Python packages (`common`, `betfair_scraper`, `paddypower_scraper`, `arb_finder`).

- [ ] **Step 2: Remove untracked Gradle build dirs**

```bash
rm -rf .gradle build
```

- [ ] **Step 3: Confirm no Kotlin/Gradle references remain**

Run: `grep -rn -i "gradle\|kotlin\|\.kt\b\|jdk\|jvm" --include='*.md' --include='*.sh' --include='*.toml' . | grep -v docs/superpowers/ | head`
Expected: no matches outside the historical spec/plan docs under `docs/superpowers/`.

- [ ] **Step 4: Refresh the lockfile and run the full suite**

Run: `uv sync && uv run pytest -q`
Expected: PASS — entire suite green (integration skipped).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Remove Kotlin/Gradle toolchain — repo is now pure Python"
```

---

## Plan 3 self-review checklist

- [ ] `uv run pytest -q` fully green.
- [ ] `src/` has no `main/` or `test/` Kotlin dirs; no `build.gradle.kts`, `gradlew`, `gradle/`.
- [ ] `grep -rni 'gradle\|kotlin\|jdk' --include='*.md' --include='*.sh' --include='*.toml' .` finds nothing outside `docs/superpowers/`.
- [ ] `./run.sh` (with valid credentials + network) runs Betfair → PaddyPower → arb and writes all three JSON files; without credentials, the Betfair stage exits non-zero and halts the pipeline (correct fail-fast).
- [ ] `uv run python -m arb_finder.validate arbs.json` reports VALID on a produced file.
- [ ] All three validators accept their own writers' output (golden tests green).

## End-to-end verification (manual, needs creds + network)

- [ ] `./run.sh gb-ie` completes; `betfair.json`, `paddypower.json`, `arbs.json` all exist and validate.
- [ ] Optional: `RUN_INTEGRATION=1 uv run pytest -m integration` passes (live Betfair login + PaddyPower browser smoke).
