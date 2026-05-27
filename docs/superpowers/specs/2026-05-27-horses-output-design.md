---
status: draft
date: 2026-05-27
topic: Replace arbs.json with horses.json — every fully-priced runner + edge
---

# horses.json output

## Goal

Refactor the arb-finder stage to emit **`horses.json`**: every fully-priced
runner (PaddyPower win price + Betfair WIN lay + the matching Betfair place
lay) together with its each-way **edge**, regardless of sign. This replaces
`arbs.json` (which only listed positive-margin opportunities). The "arbs"
are now simply the rows where `edge > 0`; the consumer filters those itself.

## Motivation

`arbs.json` discards every runner whose margin is ≤ 0, so it answers only
"is there a guaranteed profit right now?" — almost always "no". The richer
question is "for every runner we *can* price both sides of, how close is it
to an arb?". That view (the per-runner edge, including negatives) is what
makes the data useful for spotting near-misses and watching prices move,
and it's a strict superset of the old arbs output.

## Non-goals

- **Not changing the join or the edge math.** The PaddyPower↔Betfair join
  (race by `betfairWinMarketId`, runner by `selectionId`) and the
  `each_way_arb_margin` formula are unchanged. Only the *filter* (drop the
  `edge <= 0` skip) and the *output shape/name* change.
- **Not keeping `arbs.json`.** It is removed (model, validator, writer,
  CLI default, validate entry, and tests) and replaced by the horses
  equivalents. Any external consumer that read `arbs.json` must switch to
  `horses.json` and filter `edge > 0` for the old behaviour.
- **Not renaming the `arb_finder` package** or its entry points / `run.sh`
  command. It remains the edge/arb calculator; only its output changes.
- **Not adding lay-stake recommendations** or any field beyond PP price,
  BF win/place prices, and edge (YAGNI).
- **Not touching the Betfair or PaddyPower scrapers**, their schemas, or
  `betfair.json` / `paddypower.json`.

## Scope of "fully-priced"

A runner appears in `horses.json` iff ALL of the following hold (identical
to the current `find_arbs` inclusion conditions, minus the margin filter):

- its PaddyPower race has a `betfairWinMarketId` that matches a Betfair race;
- the PaddyPower race has `eachWayTerms` whose `places` maps to a `TOP_N`
  (2..5) that is present in the Betfair race's markets;
- the runner has a `selectionId` matching a Betfair runner;
- PaddyPower `winPrice` and `winPriceRaw` are both non-null;
- the Betfair WIN lay and the matching place (`TOP_N`) lay are both
  present and > 0.

Runners failing any of these are omitted (no null rows — see the "Which
horses" decision: fully-priced only).

## Output schema — `horses.json`

```json
{
  "computedAt": "2026-05-27T20:34:11Z",
  "betfairScrapedAt": "2026-05-27T20:34:01Z",
  "paddypowerScrapedAt": "2026-05-27T20:34:05Z",
  "horseCount": 7,
  "horses": [
    {
      "venue": "Finger Lakes",
      "country": "US",
      "offTime": "2026-05-27T21:47:00+01:00",
      "marketName": "21:47 Finger Lakes",
      "betfairWinMarketId": "1.258619108",
      "runner": { "name": "Emerald Forest", "selectionId": 12345678 },
      "paddypower": {
        "winPrice": 2.88,
        "winPriceRaw": "15/8",
        "eachWayTerms": { "fraction": 0.25, "places": 2 }
      },
      "betfair": { "winLay": 2.92, "placeLay": 1.64, "placeMarket": "TOP_2" },
      "edge": -0.0599
    }
  ]
}
```

- `horses` is sorted by `edge` **descending** (best / closest-to-arb first).
- `edge` is the signed decimal each-way margin per £1 PaddyPower stake
  (`each_way_arb_margin(p, f, bw, bp)`); negatives are kept.
- `horseCount == len(horses)`.
- Top-level and per-horse field order match the example above.
- `placeMarket` is the `MarketType` name (`TOP_2`..`TOP_5`) of the place
  market used for `placeLay`.

## Components changed (all in `src/arb_finder/`)

No new files. The four existing modules are refactored from the "arb"
framing to the "horses" framing.

### `models.py`

- `Arb` → `Horse`: same fields, but `margin: float` → `edge: float`.
- `BetfairLayLeg`: `top_n_lay` → `place_lay`, `top_n_type` → `place_market`.
- `ArbRunner` → `Runner` (`name`, `selection_id`). `PaddyPriceLeg` is
  reused unchanged.
- `ArbOutput` → `HorsesOutput`: `arb_count` → `horse_count`,
  `arbs` → `horses`.
- `ARB_RENAME` → `HORSES_RENAME`, adding `place_lay→placeLay`,
  `place_market→placeMarket`, `horse_count→horseCount`, dropping the
  arb-only keys. `write_arbs_json` → `write_horses_json(out, path)`.

### `calculator.py`

- `find_arbs(betfair, paddy)` → `find_horses(betfair, paddy) -> list[Horse]`.
  Identical join and `each_way_arb_margin` call; **remove** the
  `if margin <= 0.0: continue` line so every fully-priced runner is kept.
  Build a `Horse` with `edge=margin`. Sort `out` by `edge` descending.
- `each_way_arb_margin` is unchanged.

### `validation.py`

- `validate_arbs_output` → `validate_horses_output(text) -> list[str]`.
  Same structure as today with these changes:
  - top-level: `arbCount`→`horseCount`, `arbs`→`horses`, count parity on
    `horses`.
  - per-horse: `betfair.topNLay`→`placeLay` (number), `topNType`→
    `placeMarket` (string in `{TOP_2,TOP_3,TOP_4,TOP_5}`).
  - `edge` must be a number (int/float, not bool); **no sign constraint**
    (the old `margin must be > 0` rule is deleted).
  - everything else (ISO timestamps, runner name/selectionId, paddypower
    leg with `winPrice`/`winPriceRaw`/`eachWayTerms` fraction in (0,1] and
    places in 2..5) is carried over unchanged.

### `cli.py`

- `parse_arb_cli_args` → `parse_horses_cli_args`: 0 args → defaults
  `("betfair.json", "paddypower.json", "horses.json")`; 3 args → explicit;
  else `ValueError`.
- `main`: read + validate both inputs (`validate_scrape_output` /
  `validate_paddy_output`, exit 2 on failure), deserialize, call
  `find_horses`, write `HorsesOutput(computed_at, betfair_scraped_at,
  paddypower_scraped_at, horse_count=len(horses), horses)` via
  `write_horses_json`. Stdout summary: `Wrote {out} ({n} horses from {bf}
  BF races and {pp} PP races)`. Exit codes unchanged (0 ok incl. zero
  horses, 1 bad args, 2 input error).

### `validate.py`

- Default path `horses.json`; calls `validate_horses_output`.

### Outside `arb_finder`

- `run.sh`: the final stage command is unchanged (`uv run python -m
  arb_finder`); it now writes `horses.json`. No edit needed unless the
  comment names the output.
- `README.md`: replace `arbs.json` references and the
  `python -m arb_finder.validate arbs.json` example with `horses.json`.
- `.gitignore`: add `horses.json`; the now-unused `arbs.json` ignore line
  may be left or removed (harmless either way) — remove it for tidiness.

## Edge cases

- **Zero fully-priced runners** (common): `horses.json` is written with
  `horseCount: 0`, `horses: []`, exit 0 — same legitimate-empty semantics
  the arb finder has today.
- **Negative edge**: kept and valid. This is the headline behavioural
  change versus `arbs.json`.
- **Non-positive lay (≤ 0)**: still skipped (existing guard) — prevents a
  `ZeroDivisionError` and is not a real price.
- **Multiple Betfair markets for the same `TOP_N`**: already merged
  per-runner-best upstream in the Betfair scraper; `find_horses` sees one
  lay per `TOP_N` and is unaffected.

## Testing

Refactor the arb tests to the horses framing. The headline new assertion:
negative-edge runners are kept (not filtered) and validate cleanly.

- **`tests/test_calculator.py`**: `find_horses` keeps positive AND negative
  edges; skips each non-joinable case (no `betfairWinMarketId` match, no
  `eachWayTerms`, places→no `TOP_N`, `TOP_N` absent from BF markets, no
  runner match, null PP price, missing/≤0 WIN or place lay); output sorted
  by `edge` descending. `each_way_arb_margin` value tests unchanged.
- **`tests/test_arb_models.py`** (→ horses): `Horse`/`HorsesOutput`
  serialize to the schema — `edge`, `betfair.placeLay`/`placeMarket`,
  `horseCount`, top-level + per-horse key order; empty-`horses` case.
- **`tests/test_arb_validation.py`** (→ horses): `validate_horses_output`
  accepts a populated payload **with a negative edge**; rejects non-numeric
  `edge`, bad `placeMarket`, `eachWayTerms.places` out of 2..5,
  `horseCount` mismatch, missing per-horse fields; empty-horses valid.
- **`tests/test_arb_cli.py`** (→ horses): writes `horses.json` (default and
  explicit paths); missing input → exit 2; invalid input → exit 2; bad
  arity → exit 1; happy path asserts a **negative-edge** horse is present
  (proves no filtering) and `betfairScrapedAt`/`paddypowerScrapedAt`
  passthrough.
- **`tests/test_arb_golden.py`** (→ horses): `write_horses_json` output
  passes `validate_horses_output` for a populated payload (incl. a negative
  edge) and for the empty case.

Full `uv run pytest` stays green. No change to the Betfair/PaddyPower
scraper tests or their golden fixtures.

### Manual verification

Run `./run.sh us` (or `gb-ie` during racing hours) and confirm
`horses.json` is written, `uv run python -m arb_finder.validate
horses.json` reports VALID, and a known negative-edge runner (e.g. the
Finger Lakes field) appears with its `edge`.

## Risks

- **External consumer breakage.** Anything reading `arbs.json` must move to
  `horses.json` + filter `edge > 0`. The output files are gitignored and
  local; the only known consumer is a (separate) static site, out of this
  repo's scope. Called out so it isn't a surprise.
- **Test churn.** Five test files are renamed/rewritten; the risk is a
  missed assertion, mitigated by the golden round-trip + the explicit
  negative-edge assertions.
