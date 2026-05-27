---
status: draft
date: 2026-05-27
topic: Capture Betfair's standard "To Be Placed" market as a TOP_N lay source
---

# Betfair "To Be Placed" capture

## Goal

Make the Betfair scraper capture Betfair's standard **"To Be Placed"**
market (not just the explicit `N TBP` / `Top N Finish` markets), mapping
it to the right `TOP_N` lay slot via the market book's `numberOfWinners`.
This closes a coverage gap that makes the arb finder blind to legitimate
place-leg hedges.

## Motivation

For a given race Betfair lists several place-type markets. Example —
Kempton 21:00 (`raceId 1.258587732`, observed live 2026-05-27):

| marketId | name | marketType | numberOfWinners (book) |
|---|---|---|---|
| `1.258587733` | **To Be Placed** | PLACE | **3** |
| `1.258587735` | 2 TBP | OTHER_PLACE | 2 |
| `1.258587736` | 4 TBP | OTHER_PLACE | 4 |

The scraper's classifier (`classify_top_n`) only accepts the explicit
`N TBP` / `Top N Finish` names and **deliberately drops "To Be Placed"**.
So this race was recorded with `WIN, TOP_2, TOP_4` — the de-facto
**TOP_3** (the standard "To Be Placed" market, paying 3) was thrown away.

This matters because PaddyPower's each-way bets mostly pay the *standard*
number of places (2/3/4), and Betfair frequently exposes that exact count
**only** via "To Be Placed" (no explicit `N TBP` for that N). Whenever
PaddyPower's place count has no matching explicit Betfair market, the arb
finder cannot evaluate that race's place leg at all — a material part of
the "0 arbs" outcome.

This is a pre-existing limitation carried over from the original Kotlin
scraper, surfaced by running the migrated pipeline against live data.

## Non-goals

- **No output-schema change.** `betfair.json` keeps its exact shape:
  `marketScrapedAt` / `lay` keyed by `WIN` / `TOP_2..TOP_5`. The arb
  finder, all schema validators, and `arbs.json` are untouched. The only
  observable difference is that more races now carry a populated `TOP_N`.
- **No new HTTP calls.** The PLACE catalogue already returns "To Be
  Placed" (it was parsed then dropped), and we already book every market
  id; we now also book the "To Be Placed" ids — a few more ids inside the
  existing ≤40-id chunks.
- **No change to PaddyPower or arb logic.** This is purely a Betfair-side
  market-capture fix.
- **No per-bookmaker generalization, no concurrency changes.**

## Key decisions

1. **Capture "To Be Placed"** in addition to the explicit markets,
   routing by `description.marketType` (`PLACE` = standard place market,
   `OTHER_PLACE` = explicit "N TBP"), with name as a defensive fallback.
2. **Place count** for "To Be Placed" comes from the **market book's
   `numberOfWinners`** — the catalogue projection returns it as `null`,
   but the book carries it (confirmed live: `numberOfWinners=3`). We
   already book every market, so this is free.
3. **Collision rule = per-runner best (merge).** When more than one place
   market resolves to the same `TOP_N` for a race (e.g. an explicit
   `3 TBP` *and* a "To Be Placed" that also pays 3), each runner's lay is
   the **lowest non-null lay across those markets** (lower lay → higher
   each-way margin; you'd lay each selection in whichever book is
   cheapest). The single-market case is a no-op of this same merge.

## Design

### Components changed

No new files. The two modules that already own this:

#### `betfair_scraper/responses.py` — carry the place count through the book

- Add `number_of_winners: int | None` to `MarketBookSnapshot`, defaulting
  to `None` so every existing positional/keyword construction
  (`MarketBookSnapshot(status, lay_map)`) is unaffected.
- `lay_prices_from_book(root)` reads top-level `numberOfWinners`:
  `int` (excluding `bool`) → store it, else `None`. Populate it on the
  returned snapshot in all branches (OPEN and non-OPEN). The book field is
  present regardless of `priceProjection`, so `build_book_body` is
  unchanged.

#### `betfair_scraper/race_odds.py` — capture, defer, resolve, merge

- `PlaceMarketEntry.type` becomes `MarketType | None`. `None` marks a
  standard place market whose `TOP_N` is not yet known.
- `parse_catalogue_place_markets(text)` routes each market by its
  `description.marketType` (Betfair's authoritative type — the same field
  the request's `marketTypeCodes` filter keys on):
  - **`marketType == "PLACE"`** (the standard "To Be Placed" market)
    → entry with `type = None` (deferred; `TOP_N` resolved from the book);
  - **`marketType == "OTHER_PLACE"`** (the explicit "first N" markets)
    → `classify_top_n(name, numberOfWinners)`; a `TOP_N` → entry with that
    type, otherwise dropped (e.g. "Without Favourite", "Each Way" variants
    — unchanged behavior);
  - **`marketType` absent/other** → defensive fallback to name:
    name `"to be placed"` (case-insensitive, trimmed) → deferred entry;
    else `classify_top_n` as above.
  - All other fields (`market_id`, `event_id`, `market_time`, `runners`)
    are parsed exactly as today, including the existing `marketTime` /
    `marketId` / `event.id` presence guards.
- `place_markets_by_race_id` is **unchanged**: "To Be Placed" shares the
  WIN market's `(eventId, marketTime)` (confirmed live), so it binds to
  the correct race like any other place market.
- `join_scrapes(...)` gains the resolve + merge step, replacing the
  current "one `MarketScrape` per `place.type`, last-write-wins" loop:

  ```
  by_type: dict[MarketType, list[(entry, snapshot)]] = {}
  for place in place_markets.get(race.race_id, []):
      snap = snapshots.get(place.market_id)
      if snap is None or snap.status is not OPEN:
          continue
      tn = place.type
      if tn is None:                      # standard "To Be Placed"
          n = snap.number_of_winners
          tn = top_n_from_places(n) if isinstance(n, int) else None
      if tn is None:                      # unresolvable / N outside 2..5
          continue
      by_type.setdefault(tn, []).append((place, snap))

  for tn, items in by_type.items():
      merged: dict[int, tuple[str, float | None]] = {}  # sel -> (name, best lay)
      for entry, snap in items:
          for sel, name in entry.runners.items():
              lay = snap.lay_by_selection_id.get(sel)
              if sel not in merged:
                  merged[sel] = (name, lay)
              else:
                  prev_name, prev_lay = merged[sel]
                  merged[sel] = (prev_name, _better_lay(prev_lay, lay))
      scrapes[tn] = MarketScrape(
          type=tn, scraped_at=scraped_at,
          runners=[RunnerEntry(selection_id=sel, name=name, lay=lay)
                   for sel, (name, lay) in merged.items()],
      )
  ```

  `_better_lay(a, b)` returns the lower of two lays, ignoring `None`
  (`None` if both are `None`). The WIN `MarketScrape` is built exactly as
  today, before this loop.

### Data flow

Unchanged end to end. Per race: WIN catalogue + PLACE/OTHER_PLACE
catalogue → bind place markets by `(eventId, marketTime)` → batched
`listMarketBook` over all ids (now including "To Be Placed" ids) →
`join_scrapes` resolves deferred types from the book and merges per
`TOP_N` → `assemble_race_odds` → `pivot_market_scrapes` (keys runners by
name as today; merged `TOP_N` runner order is irrelevant to the pivot).

### Why the output is identical in shape

`pivot`/`assembly`/serialization key markets by `MarketType`. Whether a
`TOP_3` slot is filled by an explicit market, a "To Be Placed" market, or
a per-runner merge of both, the result is one `TOP_3` entry in
`marketScrapedAt` and one `TOP_3` lay per runner — exactly the existing
schema. Validators and `arbs.json` are unaffected.

### Detecting the standard place market

By **`description.marketType`**, with name as a defensive fallback.
`marketType` is Betfair's authoritative market-type taxonomy — it is the
exact field the request's `marketTypeCodes=["PLACE","OTHER_PLACE"]` filter
keys on, so every returned market carries it by construction, and it is a
structured enum rather than a localizable display string. `MARKET_DESCRIPTION`
(already requested) returns it.

Live evidence (2026-05-27, GB+IE): across the place markets observed,
`description.marketType` was present on every market (zero nulls) and
`PLACE ⟺ "To Be Placed"`, `OTHER_PLACE ⟺ explicit "N TBP"`, with no
anomalies. The sample was small (end-of-day), but the structural argument
(it is the filter field) does not depend on sample size. If `marketType`
is ever missing or unexpected, the name fallback (`"to be placed"` →
deferred) preserves today's behavior — and keeps existing test fixtures
that omit `marketType` working.

## Edge cases

- **`numberOfWinners` outside 2..5** (e.g. 1 for a tiny field, or absent):
  `top_n_from_places` returns `None` → the "To Be Placed" market
  contributes nothing. No crash, no bogus slot.
- **"To Be Placed" book non-OPEN**: skipped by the existing status guard.
- **Both explicit `N TBP` and "To Be Placed" pay the same N**: merged
  per-runner-best (the contested case the collision rule addresses).
- **No "To Be Placed" market** (some races): behavior identical to today.
- **Runner present in one book but not the other**: taken from whichever
  has it; `None` lay if neither offers one.

## Testing

### `tests/test_betfair_responses.py`
- `lay_prices_from_book` populates `number_of_winners` from the book
  (`numberOfWinners=3` → `3`; absent → `None`; non-OPEN snapshot still
  carries the field, defaulting `None`).
- `MarketBookSnapshot` constructs without the new arg (default `None`).

### `tests/test_race_odds.py`
- `parse_catalogue_place_markets`: a `marketType == "PLACE"` market is
  **kept** with `type is None` (regardless of exact name); an
  `OTHER_PLACE` `"3 TBP"` → `TOP_3`; an `OTHER_PLACE` market
  `classify_top_n` rejects (e.g. `"Without Fav"`) is dropped; and the
  name fallback path (entry with no `marketType`) routes `"To Be Placed"`
  → deferred and `"2 TBP"` → `TOP_2`. (Updates the existing test that
  asserted "To Be Placed" was dropped.)
- `join_scrapes` resolution: a deferred entry with `number_of_winners=3`
  produces a `TOP_3` `MarketScrape`; `number_of_winners=1` (or `None`)
  produces no `TOP_N`.
- `join_scrapes` merge: two entries resolving to the same `TOP_N` →
  per-runner **lowest** lay; one-entry case reproduces that market's
  prices unchanged.
- **Regression (live Kempton 21:00 shape)**: a race with explicit
  `2 TBP` + `4 TBP` + `To Be Placed (numberOfWinners=3)` yields
  `marketScrapedAt` keys `WIN, TOP_2, TOP_3, TOP_4`, with the `TOP_3`
  lays sourced from the "To Be Placed" book.

### Unchanged
Golden round-trip and all schema-validator tests need no change (output
schema is identical). Full `uv run pytest` stays green.

### Manual verification
Re-run the pipeline live during racing hours and confirm previously
`TOP_3`-less races (e.g. Kempton-style 3-place handicaps) now carry a
`TOP_3`, and that `betfair.json` still validates.

## Risks

- **`numberOfWinners` reliability in the book.** Confirmed present live
  for "To Be Placed". If Betfair ever omits it, that market resolves to
  no `TOP_N` and is simply skipped (degrades to today's behavior — safe).
- **`marketType` echoed in the catalogue.** Detection relies on
  `description.marketType` being returned under the `MARKET_DESCRIPTION`
  projection. Observed present on every market (zero nulls) and it is the
  field the request filter keys on, so absence is unlikely; the name
  fallback covers it if it ever is missing.
- **Name fallback fragility.** Only reached if `marketType` is absent —
  if Betfair also renamed the standard place market the fallback would
  miss it (degrades to today's behavior). Low risk; both signals have
  been stable.
