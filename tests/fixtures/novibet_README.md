# Novibet fixtures

Captured verbatim from the live Novibet feed on **2026-07-31**, via a
headless-Chromium warmup on `https://www.novibet.ie/sports/horse-racing/4372612`
(a bare `curl` gets a Cloudflare 403). Query string on every call:
`?lang=en-IE&timeZ=GMT%20Standard%20Time&oddsR=2&usrGrp=IE`, plus the
`x-gw-*` header set documented in the design spec.

| Endpoint | Fixture |
|---|---|
| `/spt/feed/marketviews/horse-racing-overview2/4324/4372612` | `novibet_overview.json` |
| `/spt/feed/marketviews/horse-racing-race2/4324/<betContextId>` | the racecards below |

`novibet_overview.json` holds two days (Jul 31: GB 41, IRE 8, SAF 4, GER 6;
Aug 01: GB 9, AUS 7, USA 1), so it exercises today-only filtering and the
region mapping together.

## Racecards

Each is named for its **actual** each-way terms — the ones in the category
`caption`, not the ones in its `sysname`. See the warning below.

| Fixture | Race | Exercises |
|---|---|---|
| `novibet_racecard_ew_2pl_1_4.json` | Goodwood, 7 runners | 2 places at 1/4; sysname agrees |
| `novibet_racecard_ew_3pl_1_5.json` | Wolverhampton, 10 runners | 3 places at 1/5; sysname agrees |
| `novibet_racecard_ew_4pl_1_5_boost_mismatch.json` | Goodwood, 15 runners | **sysname `3_4` vs caption 4 places 1/5** |
| `novibet_racecard_ew_5pl_1_5_boost_mismatch.json` | Galway, 18 runners | **sysname `2_5` vs caption 5 places 1/5** |
| `novibet_racecard_ew_6pl_1_5_boost.json` | Goodwood, 18 runners, 4 non-runners | 6 places → unpriceable (Betfair stops at TOP_5); non-runner exclusion |
| `novibet_racecard_no_eachway.json` | Musselburgh, 5 runners | small field, no each-way market offered at all |
| `novibet_racecard_near_off.json` | Goodwood, 15 runners, 3 non-runners | 1 minute from the off — each-way market already pulled, win market still live |
| `novibet_racecard_no_markets.json` | Fairview (SAF), at the off | `marketCategories: []` — everything withdrawn |

## The each-way sysname is not trustworthy

Each-way terms appear as a single market category per race, e.g.
`HORSE_RACING_RACE_WINNER_EACHWAY_3_5` captioned `"E/W 1/5 - 3 Places"`.
The sysname *looks* like it encodes `<places>_<divisor>` — and usually does.

**It is wrong on Place Boost races.** Across 30 GB/IRE races scanned on
2026-07-31: 22 agreed, **5 disagreed**, 3 had no each-way market. Every
disagreement was a `Place Boost` race, where the sysname keeps the *base*
terms while the caption advertises the *boosted* ones actually on offer:

```
sysname 3_4  ->  caption "Place Boost 1/5 - 4 Places"   (x4)
sysname 2_5  ->  caption "Place Boost 1/5 - 5 Places"   (x1)
```

Note that some Place Boost races *do* agree (the `6_5` fixture is one), so
"is it a boost?" is not a usable signal either.

**Parse the caption.** `1/(\d+)\s*-\s*(\d+)\s*Places?` handles both the
`E/W` and `Place Boost` prefixes (19 and 8 of the 30 respectively). Trusting
the sysname on the `4pl_1_5` fixture would price it as 3 places at 1/4:
an inflated place fraction *and* a comparison against Betfair's `TOP_3` lay
instead of `TOP_4` — both errors biased toward reporting arbs that are not
there.
