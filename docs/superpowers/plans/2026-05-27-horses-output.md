# horses.json Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `arb_finder` stage to write `horses.json` — every fully-priced runner with its signed each-way `edge` — replacing `arbs.json` (which only kept positive-margin rows).

**Architecture:** Pure refactor of the four `src/arb_finder/` modules from the "arb" framing to the "horses" framing: `Arb`→`Horse` (`margin`→`edge`), `ArbOutput`→`HorsesOutput`, `BetfairLayLeg.top_n_*`→`place_*`, `ArbRunner`→`Runner`, `find_arbs`→`find_horses` (drop the `edge<=0` filter, sort by edge desc), `validate_arbs_output`→`validate_horses_output` (drop the "must be > 0" rule). The PaddyPower↔Betfair join and `each_way_arb_margin` formula are unchanged. Because these modules + the golden test reference each other, the rename is one atomic commit; docs/gitignore and verification follow.

**Tech Stack:** Python 3.11+, pytest, `uv run pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-27-horses-output-design.md`

---

### Task 1: Refactor `arb_finder` to the horses framing (atomic)

**Files:**
- Modify: `src/arb_finder/models.py`, `src/arb_finder/calculator.py`, `src/arb_finder/validation.py`, `src/arb_finder/cli.py`, `src/arb_finder/validate.py`
- Rewrite: `tests/test_calculator.py`
- Create: `tests/test_horses_models.py`, `tests/test_horses_validation.py`, `tests/test_horses_cli.py`, `tests/test_horses_golden.py`
- Delete: `tests/test_arb_models.py`, `tests/test_arb_validation.py`, `tests/test_arb_cli.py`, `tests/test_arb_golden.py`

- [ ] **Step 1: Replace the tests (write the failing target state)**

Delete the four old arb test files:
```bash
git rm tests/test_arb_models.py tests/test_arb_validation.py tests/test_arb_cli.py tests/test_arb_golden.py
```

Create `tests/test_horses_models.py`:
```python
"""Tests for arb_finder.models (horses.json) serialization."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    BetfairLayLeg,
    Horse,
    HorsesOutput,
    PaddyPriceLeg,
    Runner,
    write_horses_json,
)


def _sample() -> HorsesOutput:
    return HorsesOutput(
        computed_at="2026-05-27T20:34:11Z",
        betfair_scraped_at="2026-05-27T20:34:01Z",
        paddypower_scraped_at="2026-05-27T20:34:05Z",
        horse_count=1,
        horses=[
            Horse(
                venue="Finger Lakes",
                country="US",
                off_time="2026-05-27T21:47:00+01:00",
                market_name="21:47 Finger Lakes",
                betfair_win_market_id="1.258619108",
                runner=Runner(name="Emerald Forest", selection_id=12345678),
                paddypower=PaddyPriceLeg(
                    win_price=2.88, win_price_raw="15/8",
                    each_way_terms=EachWayTerms(fraction=0.25, places=2)),
                betfair=BetfairLayLeg(
                    win_lay=2.92, place_lay=1.64, place_market=MarketType.TOP_2),
                edge=-0.0599,
            )
        ],
    )


def test_serialize_shape(tmp_path: Path):
    target = tmp_path / "horses.json"
    write_horses_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert list(payload.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "horseCount", "horses",
    ]
    h = payload["horses"][0]
    assert list(h.keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "edge",
    ]
    assert h["runner"] == {"name": "Emerald Forest", "selectionId": 12345678}
    assert h["paddypower"] == {
        "winPrice": 2.88, "winPriceRaw": "15/8",
        "eachWayTerms": {"fraction": 0.25, "places": 2}}
    assert h["betfair"] == {"winLay": 2.92, "placeLay": 1.64, "placeMarket": "TOP_2"}
    assert h["edge"] == -0.0599  # negative edge is kept


def test_empty_horses(tmp_path: Path):
    out = HorsesOutput("2026-05-27T20:34:11Z", "2026-05-27T20:34:01Z",
                       "2026-05-27T20:34:05Z", 0, [])
    target = tmp_path / "horses.json"
    write_horses_json(out, target)
    assert json.loads(target.read_text())["horses"] == []
```

Create `tests/test_horses_validation.py`:
```python
"""Tests for arb_finder.validation (horses.json)."""

from __future__ import annotations

import json

from arb_finder.validation import validate_horses_output


def _valid() -> dict:
    return {
        "computedAt": "2026-05-27T20:34:11Z",
        "betfairScrapedAt": "2026-05-27T20:34:01Z",
        "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
        "horseCount": 1,
        "horses": [{
            "venue": "Finger Lakes", "country": "US",
            "offTime": "2026-05-27T21:47:00+01:00", "marketName": "21:47 Finger Lakes",
            "betfairWinMarketId": "1.258619108",
            "runner": {"name": "Emerald Forest", "selectionId": 12345678},
            "paddypower": {"winPrice": 2.88, "winPriceRaw": "15/8",
                           "eachWayTerms": {"fraction": 0.25, "places": 2}},
            "betfair": {"winLay": 2.92, "placeLay": 1.64, "placeMarket": "TOP_2"},
            "edge": -0.0599,
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_horses_output(json.dumps(p))


def test_valid_with_negative_edge():
    assert _v(_valid()) == []


def test_empty_horses_valid():
    p = {"computedAt": "2026-05-27T20:34:11Z",
         "betfairScrapedAt": "2026-05-27T20:34:01Z",
         "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
         "horseCount": 0, "horses": []}
    assert _v(p) == []


def test_not_json():
    errs = validate_horses_output("{bad")
    assert errs and "not valid JSON" in errs[0]


def test_horse_count_mismatch():
    p = _valid(); p["horseCount"] = 5
    assert any("horseCount" in e for e in _v(p))


def test_edge_not_number():
    p = _valid(); p["horses"][0]["edge"] = "lots"
    assert any("edge" in e for e in _v(p))


def test_missing_edge():
    p = _valid(); del p["horses"][0]["edge"]
    assert any("edge" in e for e in _v(p))


def test_bad_place_market():
    p = _valid(); p["horses"][0]["betfair"]["placeMarket"] = "TOP_9"
    assert any("placeMarket" in e for e in _v(p))


def test_place_lay_not_number():
    p = _valid(); p["horses"][0]["betfair"]["placeLay"] = "x"
    assert any("placeLay" in e for e in _v(p))


def test_eachway_places_out_of_range():
    p = _valid(); p["horses"][0]["paddypower"]["eachWayTerms"]["places"] = 6
    assert any("places must be in" in e for e in _v(p))


def test_missing_runner_selection_id():
    p = _valid(); del p["horses"][0]["runner"]["selectionId"]
    assert any("selectionId" in e for e in _v(p))
```

Create `tests/test_horses_cli.py`:
```python
"""Tests for the arb_finder CLI (writes horses.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arb_finder.cli import main, parse_horses_cli_args


class TestParseArgs:
    def test_defaults(self):
        assert parse_horses_cli_args([]) == ("betfair.json", "paddypower.json", "horses.json")

    def test_explicit(self):
        assert parse_horses_cli_args(["a", "b", "c"]) == ("a", "b", "c")

    def test_bad_arity(self):
        with pytest.raises(ValueError):
            parse_horses_cli_args(["only-one"])


def _write_betfair(path: Path):
    # WIN lay 4.0 + TOP_2 lay 3.0 → a NEGATIVE edge (proves no filtering).
    path.write_text(json.dumps({
        "scrapedAt": "2026-05-25T17:05:56.890289Z", "raceCount": 1,
        "races": [{
            "raceId": "1.1", "venue": "Ascot", "country": "GB",
            "offTime": "2026-05-25T18:00:00+01:00", "winMarketUrl": "u",
            "marketName": "18:00 Ascot",
            "marketScrapedAt": {"WIN": "2026-05-25T17:05:58Z",
                                "TOP_2": "2026-05-25T17:05:58Z"},
            "runners": [{"name": "A", "lay": {"WIN": 4.0, "TOP_2": 3.0},
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
                         "winPrice": 2.0, "winPriceRaw": "1/1"}],
        }],
    }))


def test_happy_path_writes_horses_including_negative_edge(tmp_path: Path):
    bf = tmp_path / "betfair.json"; _write_betfair(bf)
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    out = tmp_path / "horses.json"
    rc = main([str(bf), str(pp), str(out)],
              now=lambda: datetime(2026, 5, 25, 17, 6, 8, tzinfo=timezone.utc))
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["horseCount"] == 1
    assert payload["horses"][0]["runner"]["selectionId"] == 1
    assert payload["horses"][0]["edge"] < 0  # kept despite negative edge
    assert payload["betfairScrapedAt"] == "2026-05-25T17:05:56.890289Z"


def test_missing_input_exits_2(tmp_path: Path):
    assert main([str(tmp_path / "nope.json"), str(tmp_path / "nope2.json"),
                 str(tmp_path / "horses.json")]) == 2


def test_invalid_betfair_exits_2(tmp_path: Path):
    bf = tmp_path / "betfair.json"; bf.write_text('{"scrapedAt":"nope","raceCount":0,"races":[]}')
    pp = tmp_path / "paddypower.json"; _write_paddy(pp)
    assert main([str(bf), str(pp), str(tmp_path / "horses.json")]) == 2


def test_bad_arity_exits_1(tmp_path: Path):
    assert main(["only-one"]) == 1
```

Create `tests/test_horses_golden.py`:
```python
"""The horses writer's output must pass the horses validator (in-process gate)."""

from __future__ import annotations

from pathlib import Path

from common.markettype import MarketType
from paddypower_scraper.models import EachWayTerms
from arb_finder.models import (
    BetfairLayLeg, Horse, HorsesOutput, PaddyPriceLeg, Runner, write_horses_json,
)
from arb_finder.validation import validate_horses_output


def test_written_horses_validate_with_negative_edge(tmp_path: Path):
    out = HorsesOutput(
        computed_at="2026-05-27T20:34:11Z",
        betfair_scraped_at="2026-05-27T20:34:01Z",
        paddypower_scraped_at="2026-05-27T20:34:05Z",
        horse_count=1,
        horses=[Horse(
            venue="Finger Lakes", country="US",
            off_time="2026-05-27T21:47:00+01:00", market_name="21:47 Finger Lakes",
            betfair_win_market_id="1.258619108",
            runner=Runner("Emerald Forest", 12345678),
            paddypower=PaddyPriceLeg(2.88, "15/8", EachWayTerms(0.25, 2)),
            betfair=BetfairLayLeg(2.92, 1.64, MarketType.TOP_2),
            edge=-0.0599)],
    )
    target = tmp_path / "horses.json"
    write_horses_json(out, target)
    assert validate_horses_output(target.read_text()) == []


def test_empty_horses_validate(tmp_path: Path):
    out = HorsesOutput("2026-05-27T20:34:11Z", "2026-05-27T20:34:01Z",
                       "2026-05-27T20:34:05Z", 0, [])
    target = tmp_path / "horses.json"
    write_horses_json(out, target)
    assert validate_horses_output(target.read_text()) == []
```

Replace the WHOLE of `tests/test_calculator.py` with:
```python
"""Tests for arb_finder.calculator (find_horses + each-way edge)."""

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
from arb_finder.calculator import each_way_arb_margin, find_horses


class TestEdgeFormula:
    def test_known_value(self):
        # p=3, f=0.2, bw=2.0, bp=1.4 → 0.75 + 0.5 - 1 = 0.25
        assert each_way_arb_margin(3.0, 0.2, 2.0, 1.4) == pytest.approx(0.25)

    def test_negative(self):
        assert each_way_arb_margin(2.0, 0.2, 4.0, 3.0) < 0


def _betfair(win_lay, place_lay) -> ScrapeOutput:
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
                name="A", lay={MarketType.WIN: win_lay, MarketType.TOP_2: place_lay},
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


class TestFindHorses:
    def test_positive_edge_included(self):
        horses = find_horses(_betfair(2.0, 1.4), _paddy())
        assert len(horses) == 1
        assert horses[0].runner.selection_id == 1
        assert horses[0].betfair.place_market is MarketType.TOP_2
        assert horses[0].betfair.place_lay == 1.4
        assert horses[0].edge == pytest.approx(0.25)

    def test_negative_edge_still_included(self):
        # The headline change vs arbs.json: negative edges are KEPT.
        horses = find_horses(_betfair(4.0, 3.0), _paddy())
        assert len(horses) == 1
        assert horses[0].edge < 0

    def test_skip_when_place_market_absent(self):
        bf = _betfair(2.0, 1.4)
        race = bf.races[0]
        bf.races[0] = RaceOdds(
            race_id=race.race_id, venue=race.venue, country=race.country,
            off_time=race.off_time, win_market_url=race.win_market_url,
            market_name=race.market_name,
            market_scraped_at={MarketType.WIN: "2026-05-25T17:05:58Z"},
            runners=[RunnerOdds("A", {MarketType.WIN: 2.0}, 1)])
        assert find_horses(bf, _paddy()) == []

    def test_skip_zero_lay(self):
        assert find_horses(_betfair(0.0, 1.4), _paddy()) == []
        assert find_horses(_betfair(2.0, 0.0), _paddy()) == []

    def test_sorted_by_edge_desc(self):
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
        horses = find_horses(bf, paddy)
        assert [h.edge for h in horses] == sorted([h.edge for h in horses], reverse=True)
        assert horses[0].runner.selection_id == 2  # B (1.2 place lay) has the higher edge
```

- [ ] **Step 2: Run the new/changed tests to verify they fail**

Run: `uv run pytest tests/test_horses_models.py tests/test_horses_validation.py tests/test_horses_cli.py tests/test_horses_golden.py tests/test_calculator.py -q`
Expected: FAIL — `ImportError`/`cannot import name 'Horse' / 'HorsesOutput' / 'Runner' / 'write_horses_json' / 'find_horses' / 'validate_horses_output' / 'parse_horses_cli_args'` (the source still uses the arb names).

- [ ] **Step 3: Rewrite `src/arb_finder/models.py`** (whole file):

```python
"""Dataclasses mirroring horses.json + serializer."""

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
    place_lay: float
    place_market: MarketType


@dataclass(frozen=True)
class Runner:
    name: str
    selection_id: int


@dataclass(frozen=True)
class Horse:
    venue: str
    country: str
    off_time: str
    market_name: str
    betfair_win_market_id: str
    runner: Runner
    paddypower: PaddyPriceLeg
    betfair: BetfairLayLeg
    edge: float


@dataclass(frozen=True)
class HorsesOutput:
    computed_at: str
    betfair_scraped_at: str
    paddypower_scraped_at: str
    horse_count: int
    horses: list[Horse]


HORSES_RENAME = {
    "computed_at": "computedAt",
    "betfair_scraped_at": "betfairScrapedAt",
    "paddypower_scraped_at": "paddypowerScrapedAt",
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


def write_horses_json(out: HorsesOutput, path: Path | str) -> None:
    write_json(out, HORSES_RENAME, path)
```

- [ ] **Step 4: Rewrite `src/arb_finder/calculator.py`** (whole file):

```python
"""Each-way edge + the join that prices every fully-priced runner."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places
from betfair_scraper.models import ScrapeOutput
from paddypower_scraper.models import PaddyOutput
from .models import BetfairLayLeg, Horse, PaddyPriceLeg, Runner


def each_way_arb_margin(p: float, f: float, bw: float, bp: float) -> float:
    """Each-way edge per £1 PaddyPower stake (signed):

      L_w  = p / (2·bw)
      L_p  = (1 + (p−1)·f) / (2·bp)
      edge = L_w + L_p − 1
    """
    lw = p / (2.0 * bw)
    lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0


def find_horses(betfair: ScrapeOutput, paddy: PaddyOutput) -> list[Horse]:
    """Every fully-priced runner with its each-way edge, sorted by edge
    descending. A runner is included when its PaddyPower win price, the
    Betfair WIN lay, and the Betfair place (TOP_N matching PP's places) lay
    are all present and > 0. The edge may be negative."""
    betfair_by_id = {r.race_id: r for r in betfair.races}
    out: list[Horse] = []

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
        place_market = top_n_from_places(ew.places)
        if place_market is None or place_market not in br.market_scraped_at:
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
            place_lay = brun.lay.get(place_market)
            if (win_lay is None or place_lay is None
                    or win_lay <= 0.0 or place_lay <= 0.0):
                continue

            edge = each_way_arb_margin(p=pp_price, f=ew.fraction, bw=win_lay, bp=place_lay)
            out.append(Horse(
                venue=pr.venue,
                country=pr.country,
                off_time=pr.off_time,
                market_name=pr.market_name,
                betfair_win_market_id=win_market_id,
                runner=Runner(name=prun.name, selection_id=sel),
                paddypower=PaddyPriceLeg(
                    win_price=pp_price, win_price_raw=pp_raw, each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, place_lay=place_lay, place_market=place_market),
                edge=edge,
            ))

    out.sort(key=lambda h: h.edge, reverse=True)
    return out
```

- [ ] **Step 5: Rewrite `src/arb_finder/validation.py`** (whole file):

```python
"""Validate a horses.json payload string."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(2, 6)  # 2..5 inclusive
_ALLOWED_PLACE_MARKETS = {"TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_horses_output(text: str) -> list[str]:
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
    horse_count = _require_int(root, "horseCount", errors)
    horses = root.get("horses")
    if not isinstance(horses, list):
        errors.append("horses: missing or not array")
        return errors
    if horse_count is not None and horse_count != len(horses):
        errors.append(f"horseCount ({horse_count}) != horses.length ({len(horses)})")

    for i, h in enumerate(horses):
        ctx = f"horses[{i}]"
        if not isinstance(h, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(h, "venue", errors)
        _require_str(h, "country", errors)
        _require_str(h, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(h, "marketName", errors)
        _require_str(h, "betfairWinMarketId", errors)

        edge = h.get("edge")
        if not isinstance(edge, (int, float)) or isinstance(edge, bool):
            errors.append(f"{ctx}.edge: missing or not a number")

        runner = h.get("runner")
        if not isinstance(runner, dict):
            errors.append(f"{ctx}.runner: missing or not an object")
        else:
            _require_str(runner, "name", errors)
            sel = runner.get("selectionId")
            if not isinstance(sel, (int, float)) or isinstance(sel, bool):
                errors.append(f"{ctx}.runner.selectionId: missing or not a number")

        _validate_paddy_leg(h.get("paddypower"), f"{ctx}.paddypower", errors)
        _validate_betfair_leg(h.get("betfair"), f"{ctx}.betfair", errors)
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
    for key in ("winLay", "placeLay"):
        v = el.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errors.append(f"{ctx}.{key}: missing or not a number")
    pm = el.get("placeMarket")
    if not isinstance(pm, str):
        errors.append(f"{ctx}.placeMarket: missing or not a string")
    elif pm not in _ALLOWED_PLACE_MARKETS:
        errors.append(f"{ctx}.placeMarket: '{pm}' not in {_ALLOWED_PLACE_MARKETS}")


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

- [ ] **Step 6: Rewrite `src/arb_finder/cli.py`** (whole file):

```python
"""Edge calculator entry point. Reads + validates betfair.json and
paddypower.json, prices every fully-priced runner, writes horses.json.
Exit 0 ok (even zero horses), 1 bad usage, 2 input error."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from betfair_scraper.models import ScrapeOutput
from betfair_scraper.validation import validate_scrape_output
from common.timeutil import iso_utc
from paddypower_scraper.models import PaddyOutput
from paddypower_scraper.validation import validate_paddy_output
from .calculator import find_horses
from .models import HorsesOutput, write_horses_json


def parse_horses_cli_args(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 0:
        return ("betfair.json", "paddypower.json", "horses.json")
    if len(argv) == 3:
        return (argv[0], argv[1], argv[2])
    raise ValueError(
        "usage: arb-finder                                          # all defaults\n"
        "       arb-finder <betfair-in> <paddypower-in> <horses-out>  # all explicit"
    )


def main(argv=None, *, now=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
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

- [ ] **Step 7: Rewrite `src/arb_finder/validate.py`** (whole file):

```python
"""Validate a horses.json file.
Usage: python -m arb_finder.validate [horses.json]
Exit 0 = valid, 1 = errors, 2 = file error."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_horses_output


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("horses.json")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    errors = validate_horses_output(path.read_text())
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

- [ ] **Step 8: Run the full suite to verify pass**

Run: `uv run pytest -q`
Expected: PASS. Net test count vs before: removed 4 arb test files, added 4 horses test files + rewrote test_calculator; the suite should pass with no `arb`-named symbols remaining. Also confirm nothing else imports the old names:
Run: `grep -rn "find_arbs\|ArbOutput\|write_arbs_json\|validate_arbs_output\|\.margin\|top_n_lay\|top_n_type\|parse_arb_cli_args\|ArbRunner\b" src/ tests/`
Expected: no matches.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "arb_finder: write horses.json (every fully-priced runner + edge), replacing arbs.json"
```

---

### Task 2: Update run.sh, README, .gitignore

**Files:**
- Modify: `run.sh` (only if it names `arbs.json`), `README.md`, `.gitignore`

- [ ] **Step 1: Check run.sh for arbs.json references**

Run: `grep -n "arbs" run.sh || echo "no arbs reference in run.sh"`
If a match exists, update the comment/text to `horses.json`. (The pipeline command `uv run python -m arb_finder` is unchanged; it now writes `horses.json` by default.)

- [ ] **Step 2: Update `README.md`** — replace `arbs.json` references. Specifically:
  - In the pipeline description, change the arb-finder output from `arbs.json` to `horses.json` (e.g. "**Edge calculator** → `horses.json` (every fully-priced runner with its each-way edge)").
  - In Usage, change the outputs line to list `./horses.json` instead of `./arbs.json`.
  - In "Validating output", change `uv run python -m arb_finder.validate arbs.json` to `uv run python -m arb_finder.validate horses.json`.
  - In Architecture, change the `arb_finder/` line to "joins both files → `horses.json`".

  Verify after editing: `grep -n "arbs.json" README.md || echo "no arbs.json left in README"` → expect no matches.

- [ ] **Step 3: Update `.gitignore`** — in the "Local scraper output" section, replace the `arbs.json` line with `horses.json`:

```gitignore
# Local scraper output
scraper.log
betfair.json
paddypower.json
horses.json
debug-page.html
```

Verify: `git check-ignore horses.json` → prints `horses.json` (ignored).

- [ ] **Step 4: Confirm entry points still import and the suite is green**

Run: `uv run python -c "import arb_finder.cli, arb_finder.validate; print('ok')"` → `ok`
Run: `uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add run.sh README.md .gitignore
git commit -m "docs/gitignore: arb finder now outputs horses.json"
```

---

### Task 3: Live verification

**Files:** none (verification only).

- [ ] **Step 1: Full suite + import smoke**

Run: `uv run pytest -q` → PASS (integration tests skipped).
Run: `uv run python -c "import arb_finder.cli, arb_finder.calculator, arb_finder.validation, arb_finder.models, arb_finder.validate; print('ok')"` → `ok`.

- [ ] **Step 2: (Manual, needs creds + network during racing hours) End-to-end**

Run: `./run.sh us` (US racing is the region most likely live in UK evening) — confirm the final line reads `Wrote horses.json (N horses from …)`.
Run: `uv run python -m arb_finder.validate horses.json` → `horses.json: VALID (matches spec)`.
Spot-check: `uv run python -c "import json; d=json.load(open('horses.json')); print(d['horseCount']); [print(h['runner']['name'], h['betfair']['placeMarket'], round(h['edge']*100,2)) for h in d['horses'][:10]]"` — confirm fully-priced runners appear, **including negative-edge ones** (proving no filtering), sorted by edge descending. (Skip if outside racing hours — covered by `test_horses_cli.py` / golden tests regardless.)

---

## Self-review

**Spec coverage:**
- Scope = fully-priced runners only, edge may be negative → `find_horses` (Task 1 Step 4) keeps the existing inclusion guards, drops only the `>0` filter; tested by `test_negative_edge_still_included`.
- Replace arbs.json → Task 1 renames output to `horses.json` everywhere; old arb tests deleted; Task 2 updates docs/gitignore.
- Schema (computedAt/…/horseCount/horses; runner; paddypower; betfair winLay/placeLay/placeMarket; edge; sorted desc) → `models.py` + `HORSES_RENAME` + `find_horses` sort; tested by `test_horses_models.test_serialize_shape`.
- Validator drops the ">0" rule, keeps the rest, `placeMarket` allowlist, `horseCount` parity → `validation.py` (Task 1 Step 5); tested by `test_valid_with_negative_edge` + `test_bad_place_market` + `test_horse_count_mismatch`.
- CLI defaults to horses.json, exit codes unchanged → `cli.py` (Task 1 Step 6); tested by `test_horses_cli.py`.
- `arb_finder` package name kept; `ArbRunner`→`Runner`; `each_way_arb_margin` unchanged → reflected in `models.py`/`calculator.py`.
- Empty-horses case → `test_empty_horses` (models), `test_empty_horses_valid` (validation), `test_empty_horses_validate` (golden).

**Placeholder scan:** none — complete code/commands in every step.

**Type consistency:** `Horse`/`HorsesOutput`/`Runner`/`BetfairLayLeg(win_lay, place_lay, place_market)`/`PaddyPriceLeg`, `find_horses`, `write_horses_json`, `HORSES_RENAME`, `validate_horses_output`, `parse_horses_cli_args`, `edge` — names match across `models.py`, `calculator.py`, `validation.py`, `cli.py`, `validate.py`, and all five test files. The `placeMarket` JSON key ↔ `place_market` dataclass field ↔ `HORSES_RENAME` entry are consistent; `each_way_arb_margin` is still imported by the calculator tests.
