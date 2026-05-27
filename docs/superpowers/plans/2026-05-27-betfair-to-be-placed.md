# Betfair "To Be Placed" capture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture Betfair's standard `To Be Placed` market as a `TOP_N` lay source (mapped via the market book's `numberOfWinners`), so the arb finder stops missing valid place-leg hedges (e.g. Kempton 21:00's de-facto TOP_3).

**Architecture:** Two existing modules change. `responses.py` threads the book's `numberOfWinners` onto `MarketBookSnapshot`. `race_odds.py` routes place markets by `description.marketType` (`PLACE` = standard place market, deferred; `OTHER_PLACE` = explicit `N TBP` classified by name; name fallback when `marketType` absent), then `join_scrapes` resolves each deferred market's `TOP_N` from the book and merges markets sharing a `TOP_N` per-runner (lowest non-null lay). Output schema is unchanged.

**Tech Stack:** Python 3.11+, pytest, `uv run pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-27-betfair-to-be-placed-design.md`

---

### Task 1: `MarketBookSnapshot.number_of_winners` + book parse

**Files:**
- Modify: `src/betfair_scraper/responses.py`
- Test: `tests/test_betfair_responses.py`

- [ ] **Step 1: Add failing tests** — append to `class TestLayPricesFromBook` in `tests/test_betfair_responses.py`:

```python
    def test_captures_number_of_winners(self):
        obj = {
            "status": "OPEN",
            "numberOfWinners": 3,
            "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}],
        }
        assert lay_prices_from_book(obj).number_of_winners == 3

    def test_number_of_winners_absent_is_none(self):
        obj = {"status": "OPEN", "runners": []}
        assert lay_prices_from_book(obj).number_of_winners is None

    def test_number_of_winners_present_when_non_open(self):
        snap = lay_prices_from_book({"status": "SUSPENDED", "numberOfWinners": 4, "runners": []})
        assert snap.status is MarketBookStatus.OTHER
        assert snap.number_of_winners == 4

    def test_snapshot_constructs_without_number_of_winners(self):
        snap = MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5})
        assert snap.number_of_winners is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_betfair_responses.py -q`
Expected: FAIL — `MarketBookSnapshot` has no `number_of_winners` attribute (and the constructor accepts no such field).

- [ ] **Step 3: Add the field to `MarketBookSnapshot`** in `src/betfair_scraper/responses.py` (replace the dataclass):

```python
@dataclass(frozen=True)
class MarketBookSnapshot:
    status: MarketBookStatus
    # selectionId → best lay price; value is None when availableToLay is empty.
    lay_by_selection_id: dict[int, float | None]
    # Betfair's place count for the market (book-only; catalogue returns null).
    number_of_winners: int | None = None
```

- [ ] **Step 4: Read `numberOfWinners` in `lay_prices_from_book`** — replace the whole function in `src/betfair_scraper/responses.py`:

```python
def lay_prices_from_book(root: dict) -> MarketBookSnapshot:
    n = root.get("numberOfWinners")
    number_of_winners = n if isinstance(n, int) and not isinstance(n, bool) else None
    status = (
        MarketBookStatus.OPEN if root.get("status") == "OPEN"
        else MarketBookStatus.OTHER
    )
    if status is not MarketBookStatus.OPEN:
        return MarketBookSnapshot(status, {}, number_of_winners)
    runners = root.get("runners")
    if not isinstance(runners, list):
        return MarketBookSnapshot(status, {}, number_of_winners)
    out: dict[int, float | None] = {}
    for r in runners:
        if not isinstance(r, dict):
            continue
        sel = r.get("selectionId")
        if not isinstance(sel, int) or isinstance(sel, bool):
            continue
        ex = r.get("ex")
        lays = ex.get("availableToLay") if isinstance(ex, dict) else None
        first_price = None
        if isinstance(lays, list):
            for el in lays:
                if isinstance(el, dict):
                    # First offer's price; keep only if numeric (Kotlin used
                    # .asDouble). Non-numeric/bool/null → leave as None.
                    p = el.get("price")
                    if isinstance(p, (int, float)) and not isinstance(p, bool):
                        first_price = p
                    break
        out[sel] = first_price
    return MarketBookSnapshot(status, out, number_of_winners)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_betfair_responses.py -q`
Expected: PASS (all prior tests + the 4 new ones).

- [ ] **Step 6: Commit**

```bash
git add src/betfair_scraper/responses.py tests/test_betfair_responses.py
git commit -m "betfair_scraper.responses: carry book numberOfWinners on MarketBookSnapshot"
```

---

### Task 2: Route place markets by `marketType` (capture "To Be Placed")

**Files:**
- Modify: `src/betfair_scraper/race_odds.py`
- Test: `tests/test_race_odds.py`

- [ ] **Step 1: Replace the failing test** — in `tests/test_race_odds.py`, DELETE `test_parse_catalogue_place_markets_filters_and_binds` entirely (it asserts the old "To Be Placed is dropped" behavior) and add these two in its place:

```python
def test_parse_catalogue_place_markets_routes_by_market_type():
    text = json.dumps([
        {  # explicit OTHER_PLACE → TOP_2
            "marketName": "2 TBP", "marketId": "9.1",
            "description": {"marketType": "OTHER_PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # standard PLACE → deferred (type None), kept
            "marketName": "To Be Placed", "marketId": "9.2",
            "description": {"marketType": "PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # OTHER_PLACE that doesn't classify → dropped
            "marketName": "Without Fav", "marketId": "9.3",
            "description": {"marketType": "OTHER_PLACE", "marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"}, "runners": [],
        },
    ])
    by_id = {e.market_id: e for e in parse_catalogue_place_markets(text)}
    assert set(by_id) == {"9.1", "9.2"}
    assert by_id["9.1"].type is MarketType.TOP_2
    assert by_id["9.2"].type is None          # deferred standard place market
    assert by_id["9.2"].runners == {1: "A"}


def test_parse_catalogue_place_markets_name_fallback_without_market_type():
    # No description.marketType → fall back to name matching.
    text = json.dumps([
        {"marketName": "To Be Placed", "marketId": "9.1",
         "description": {"marketTime": "2026-05-25T17:00:00Z"},
         "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}]},
        {"marketName": "2 TBP", "marketId": "9.2",
         "description": {"marketTime": "2026-05-25T17:00:00Z"},
         "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}]},
    ])
    by_id = {e.market_id: e for e in parse_catalogue_place_markets(text)}
    assert by_id["9.1"].type is None          # "To Be Placed" → deferred
    assert by_id["9.2"].type is MarketType.TOP_2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: FAIL — the new tests expect `9.2` ("To Be Placed") to be kept with `type is None`, but the current parser drops it (so `set(by_id) == {"9.1"}`).

- [ ] **Step 3: Make `PlaceMarketEntry.type` optional** — in `src/betfair_scraper/race_odds.py` replace the dataclass:

```python
@dataclass(frozen=True)
class PlaceMarketEntry:
    market_id: str
    type: MarketType | None  # None = standard "To Be Placed"; TOP_N resolved from the book
    event_id: str
    market_time: str
    runners: dict[int, str]
```

- [ ] **Step 4: Route by `marketType` in `parse_catalogue_place_markets`** — replace the whole function:

```python
def parse_catalogue_place_markets(text: str) -> list[PlaceMarketEntry]:
    arr = json.loads(text)
    out: list[PlaceMarketEntry] = []
    for el in arr:
        if not isinstance(el, dict):
            continue
        name = el.get("marketName")
        desc = el.get("description")
        if not isinstance(name, str) or not isinstance(desc, dict):
            continue
        n_winners = desc.get("numberOfWinners")
        if not isinstance(n_winners, int) or isinstance(n_winners, bool):
            n_winners = None
        market_type = desc.get("marketType")
        # Route by Betfair's authoritative marketType; fall back to name.
        if market_type == "PLACE" or (
            market_type is None and name.strip().lower() == "to be placed"
        ):
            type_ = None  # standard place market — TOP_N resolved from the book
        else:
            type_ = classify_top_n(name, n_winners)
            if type_ is None:
                continue
        market_time = desc.get("marketTime")
        market_id = el.get("marketId")
        event = el.get("event")
        if not isinstance(market_time, str) or not isinstance(market_id, str) \
                or not isinstance(event, dict):
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str):
            continue
        out.append(PlaceMarketEntry(market_id, type_, event_id, market_time, _runner_map(el)))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: PASS. (`join_scrapes` is unchanged here; no test feeds a `type is None` entry into it yet — that arrives in Task 3.)

- [ ] **Step 6: Commit**

```bash
git add src/betfair_scraper/race_odds.py tests/test_race_odds.py
git commit -m "betfair_scraper.race_odds: capture To Be Placed, route place markets by marketType"
```

---

### Task 3: Resolve + merge in `join_scrapes`

**Files:**
- Modify: `src/betfair_scraper/race_odds.py`
- Test: `tests/test_race_odds.py`

- [ ] **Step 1: Add failing tests** — append to `tests/test_race_odds.py`:

```python
def test_join_scrapes_resolves_to_be_placed_from_book():
    races = [Race("1.1", "Kempton", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"})]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.6}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert list(out[0].market_scraped_at) == [MarketType.WIN, MarketType.TOP_3]
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_3: 1.6}


def test_join_scrapes_to_be_placed_count_out_of_range_dropped():
    races = [Race("1.1", "X", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"})]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.6}, number_of_winners=1),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert list(out[0].market_scraped_at) == [MarketType.WIN]  # 1 place → no TOP_N


def test_join_scrapes_merges_contested_topn_per_runner_best():
    races = [Race("1.1", "X", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [
        PlaceMarketEntry("9.explicit", MarketType.TOP_3, "30.1", "t", {1: "A", 2: "B"}),
        PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A", 2: "B"}),
    ]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5, 2: 2.5}),
        "9.explicit": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.60, 2: 5.20}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.45, 2: 5.40}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A"), (2, "B")]}, "n", "t")
    lays = {r.name: r.lay[MarketType.TOP_3] for r in out[0].runners}
    assert lays == {"A": 3.45, "B": 5.20}  # per-runner cheapest across the two books


def test_join_scrapes_kempton_shape():
    # Live Kempton 21:00 shape: explicit 2 TBP + 4 TBP, plus To-Be-Placed paying 3.
    races = [Race("1.1", "Kempton", "GB", "2026-05-27T21:00:00+01:00", "u")]
    place = {"1.1": [
        PlaceMarketEntry("9.2", MarketType.TOP_2, "30.1", "t", {1: "A"}),
        PlaceMarketEntry("9.4", MarketType.TOP_4, "30.1", "t", {1: "A"}),
        PlaceMarketEntry("9.tbp", None, "30.1", "t", {1: "A"}),
    ]}
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.2": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 3.8}),
        "9.4": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.8}),
        "9.tbp": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.3}, number_of_winners=3),
    }
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "n", "t")
    assert set(out[0].market_scraped_at) == {
        MarketType.WIN, MarketType.TOP_2, MarketType.TOP_3, MarketType.TOP_4}
    assert out[0].runners[0].lay[MarketType.TOP_3] == 2.3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: FAIL — the current `join_scrapes` does `scrapes[place.type] = ...`, so a deferred entry (`type is None`) is never resolved to `TOP_3` (and would key `scrapes[None]`), so the resolution/merge/Kempton assertions fail.

- [ ] **Step 3: Add the `top_n_from_places` import** — in `src/betfair_scraper/race_odds.py` change:

```python
from common.markettype import MarketType
```
to:
```python
from common.markettype import MarketType, top_n_from_places
```

- [ ] **Step 4: Add the `_better_lay` helper** — in `src/betfair_scraper/race_odds.py`, immediately above `def join_scrapes(`:

```python
def _better_lay(a: "float | None", b: "float | None") -> "float | None":
    """Lower of two lay prices (a lower lay yields a higher each-way margin).
    None is treated as 'no offer'; returns None only if both are None."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a <= b else b
```

- [ ] **Step 5: Replace the place-market loop in `join_scrapes`** — replace the body of the `for race in races:` loop from the line `for place in place_markets.get(race.race_id, []):` through the end of that `for place` block (i.e. the `scrapes[place.type] = MarketScrape(...)` assignment), leaving the WIN-scrape construction above it and the `assemble_race_odds` call below it unchanged. New code:

```python
        by_type: dict[MarketType, list[tuple[PlaceMarketEntry, MarketBookSnapshot]]] = {}
        for place in place_markets.get(race.race_id, []):
            snap = snapshots.get(place.market_id)
            if snap is None or snap.status is not MarketBookStatus.OPEN:
                continue
            tn = place.type
            if tn is None:  # standard "To Be Placed" — resolve N from the book
                n = snap.number_of_winners
                tn = top_n_from_places(n) if isinstance(n, int) else None
            if tn is None:  # unresolved, or numberOfWinners outside 2..5
                continue
            by_type.setdefault(tn, []).append((place, snap))

        for tn, items in by_type.items():
            # Merge markets sharing this TOP_N: best (lowest non-null) lay per runner.
            merged: dict[int, tuple[str, float | None]] = {}
            for entry, snap in items:
                for sel, name in entry.runners.items():
                    lay = snap.lay_by_selection_id.get(sel)
                    if sel not in merged:
                        merged[sel] = (name, lay)
                    else:
                        prev_name, prev_lay = merged[sel]
                        merged[sel] = (prev_name, _better_lay(prev_lay, lay))
            scrapes[tn] = MarketScrape(
                type=tn,
                scraped_at=scraped_at,
                runners=[
                    RunnerEntry(selection_id=sel, name=name, lay=lay)
                    for sel, (name, lay) in merged.items()
                ],
            )
```

For reference, the surrounding (unchanged) frame of the loop is:

```python
    for race in races:
        win_snap = snapshots.get(race.race_id)
        if win_snap is None or win_snap.status is not MarketBookStatus.OPEN:
            continue
        name_order = win_runners.get(race.race_id)
        if name_order is None:
            continue
        scrapes: dict[MarketType, MarketScrape] = {
            MarketType.WIN: MarketScrape(... unchanged ...)
        }
        # <<< the two new blocks above replace the old `for place ...` loop here >>>
        odds = assemble_race_odds(race, win_market_name, scrapes)
        if odds is not None:
            out.append(odds)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: PASS — including the four new tests and all pre-existing `join_scrapes`/fetcher tests (their explicit-`TOP_N` entries take the `tn = place.type` path; single-entry merges reproduce the market's prices unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/betfair_scraper/race_odds.py tests/test_race_odds.py
git commit -m "betfair_scraper.race_odds: resolve To Be Placed N from book + per-runner merge"
```

---

### Task 4: Full regression + live verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (previous count + 8 new tests; 2 integration skipped). The golden round-trip and all schema-validator tests must still pass unchanged — the output schema is identical (`marketScrapedAt`/`lay` keyed by `WIN`/`TOP_2..5`).

- [ ] **Step 2: Confirm imports still resolve**

Run: `uv run python -c "import betfair_scraper.race_odds, betfair_scraper.responses; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: (Manual, needs creds + network, during racing hours) Live check**

Run: `./run.sh` then `uv run python -m betfair_scraper.validate betfair.json`
Expected: `betfair.json: VALID`. Spot-check that a 3-place handicap whose Betfair listing only had `2 TBP`/`4 TBP` explicit markets (Kempton-style) now shows `TOP_3` in its `marketScrapedAt`. (Skip if outside racing hours / no open markets — covered by the `test_join_scrapes_kempton_shape` unit test regardless.)

---

## Self-review

**Spec coverage:**
- Capture "To Be Placed" + route by `marketType` (PLACE deferred / OTHER_PLACE classify / name fallback) → Task 2.
- Place count from book `numberOfWinners` → Task 1 (carry it) + Task 3 (resolve via `top_n_from_places`).
- Per-runner-best merge on contested `TOP_N` → Task 3 (`_better_lay`).
- `numberOfWinners` outside 2..5 / absent → dropped → `test_join_scrapes_to_be_placed_count_out_of_range_dropped`.
- Output schema unchanged / validators+golden untouched → Task 4 Step 1.
- Binding unchanged (`place_markets_by_race_id`) → no task needed; existing tests still cover it.

**Placeholder scan:** none — every step has exact code/commands.

**Type consistency:** `MarketBookSnapshot(status, lay_by_selection_id, number_of_winners=None)`, `PlaceMarketEntry.type: MarketType | None`, `_better_lay(a, b)`, `top_n_from_places(n)`, `MarketScrape(type=, scraped_at=, runners=[RunnerEntry(...)])` — all consistent across tasks and with the existing modules.
