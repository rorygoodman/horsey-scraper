# Python Rewrite — Plan 2: Betfair scraper

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Kotlin Betfair scraper (`com.horsey.scraper` package, minus the `arb`/`paddypower` subpackages) to `src/betfair_scraper/`, producing a byte-shape-compatible `betfair.json` via `python -m betfair_scraper`.

**Architecture:** Leaf-first port. Pure parsers/formatters/validators first (no I/O), then the two fetchers (driven by an injected fake client), then the `urllib`-based HTTP client and the CLI. Reuses `common` from Plan 1. The Kotlin tree remains as the behavioral oracle.

**Tech Stack:** Python ≥3.11, pytest, stdlib `json`/`re`/`urllib`/`datetime`/`zoneinfo`.

**Spec:** `docs/superpowers/specs/2026-05-26-python-rewrite-design.md`

**Behavioral oracle (do not delete; removed in Plan 3):**
`src/main/kotlin/com/horsey/scraper/{Models,BetfairResponses,MarketClassifier,RunnerPivot,RaceOddsAssembly,Credentials,RaceListFetcher,RaceOddsFetcher,SchemaValidator,BetfairClient,Main}.kt` and their tests under `src/test/kotlin/com/horsey/scraper/`.

**Prerequisite:** Plan 1 complete (`common` package + green suite).

**Intentionally NOT ported:** `OffTimeBuilder.kt` (`buildOffTime`) and `RaceIdParser.kt` (`extractRaceId`) are vestigial leftovers from the retired Selenium scraper — neither is on the API scrape path. Before skipping them, confirm with `grep -rn "buildOffTime\|extractRaceId\|OffTimeBuilder\|RaceIdParser" src/main/kotlin` that the only references are their own files + tests. If some live caller is found, add a `common`/`betfair_scraper` task to port it; otherwise they (and their Kotlin tests) simply disappear when the Kotlin tree is deleted in Plan 3.

---

## Task 1: `betfair_scraper/models.py` — dataclasses, serializer, deserializer (TDD)

Oracle: `Models.kt`. Output field order matches `betfair.json`: race = `raceId, venue, country, offTime, winMarketUrl, marketName, marketScrapedAt, runners`; runner = `name, lay, selectionId`; top-level = `scrapedAt, raceCount, races`.

**Files:**
- Create: `src/betfair_scraper/models.py`
- Test: `tests/test_betfair_models.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_betfair_models.py`:
```python
"""Tests for betfair_scraper.models: dataclasses, serialize, deserialize."""

from __future__ import annotations

import json
from pathlib import Path

from common.markettype import MarketType
from betfair_scraper.models import (
    RaceOdds,
    RunnerOdds,
    ScrapeOutput,
    write_betfair_json,
)


def _sample() -> ScrapeOutput:
    return ScrapeOutput(
        scraped_at="2026-05-25T17:05:56.890289Z",
        race_count=1,
        races=[
            RaceOdds(
                race_id="1.258528220",
                venue="Ballinrobe",
                country="IE",
                off_time="2026-05-25T18:05:00+01:00",
                win_market_url="https://www.betfair.com/exchange/plus/horse-racing/market/1.258528220",
                market_name="18:05 Ballinrobe - 2m1f Beg Chs",
                market_scraped_at={
                    MarketType.WIN: "2026-05-25T17:05:58.303431Z",
                    MarketType.TOP_2: "2026-05-25T17:05:58.303431Z",
                },
                runners=[
                    RunnerOdds(
                        name="Sony Bill",
                        lay={MarketType.WIN: 2.72, MarketType.TOP_2: 1.99},
                        selection_id=66986352,
                    ),
                    RunnerOdds(
                        name="No Price",
                        lay={MarketType.WIN: None, MarketType.TOP_2: None},
                        selection_id=None,
                    ),
                ],
            )
        ],
    )


def test_serialize_shape_and_key_order(tmp_path: Path):
    target = tmp_path / "betfair.json"
    write_betfair_json(_sample(), target)
    raw = target.read_text()
    payload = json.loads(raw)

    assert list(payload.keys()) == ["scrapedAt", "raceCount", "races"]
    race = payload["races"][0]
    assert list(race.keys()) == [
        "raceId", "venue", "country", "offTime",
        "winMarketUrl", "marketName", "marketScrapedAt", "runners",
    ]
    assert list(race["runners"][0].keys()) == ["name", "lay", "selectionId"]
    assert race["marketScrapedAt"]["WIN"] == "2026-05-25T17:05:58.303431Z"
    assert race["runners"][0]["lay"] == {"WIN": 2.72, "TOP_2": 1.99}
    assert race["runners"][1]["lay"] == {"WIN": None, "TOP_2": None}
    assert race["runners"][1]["selectionId"] is None


def test_selection_id_stays_int(tmp_path: Path):
    target = tmp_path / "betfair.json"
    write_betfair_json(_sample(), target)
    payload = json.loads(target.read_text())
    assert isinstance(payload["races"][0]["runners"][0]["selectionId"], int)


def test_round_trip_from_dict():
    out = _sample()
    # serialize → dict → from_dict should reproduce the dataclass tree
    import tempfile, os
    fd, name = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    write_betfair_json(out, name)
    reloaded = ScrapeOutput.from_dict(json.loads(Path(name).read_text()))
    os.unlink(name)
    assert reloaded == out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_betfair_models.py -q`
Expected: FAIL — `ModuleNotFoundError: betfair_scraper.models`.

- [ ] **Step 3: Implement `src/betfair_scraper/models.py`**

```python
"""Dataclasses mirroring betfair.json + serialize/deserialize.

snake_case fields; the snake→camel rename happens at the JSON boundary
via common.jsonio. MarketType enum keys/values serialize as their .name."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.jsonio import write_json
from common.markettype import MarketType

# ---- internal (not serialized) intermediate types ----


@dataclass(frozen=True)
class Race:
    race_id: str
    venue: str
    country: str
    off_time: str
    win_market_url: str


@dataclass(frozen=True)
class RunnerEntry:
    selection_id: int | None
    name: str
    lay: float | None


@dataclass(frozen=True)
class MarketScrape:
    type: MarketType
    scraped_at: str
    runners: list[RunnerEntry]


# ---- serialized output types ----


@dataclass(frozen=True)
class RunnerOdds:
    name: str
    lay: dict[MarketType, float | None]
    selection_id: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunnerOdds":
        return cls(
            name=d["name"],
            lay={MarketType[k]: v for k, v in d["lay"].items()},
            selection_id=d.get("selectionId"),
        )


@dataclass(frozen=True)
class RaceOdds:
    race_id: str
    venue: str
    country: str
    off_time: str
    win_market_url: str
    market_name: str
    market_scraped_at: dict[MarketType, str]
    runners: list[RunnerOdds]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RaceOdds":
        return cls(
            race_id=d["raceId"],
            venue=d["venue"],
            country=d["country"],
            off_time=d["offTime"],
            win_market_url=d["winMarketUrl"],
            market_name=d["marketName"],
            market_scraped_at={
                MarketType[k]: v for k, v in d["marketScrapedAt"].items()
            },
            runners=[RunnerOdds.from_dict(r) for r in d.get("runners", [])],
        )


@dataclass(frozen=True)
class ScrapeOutput:
    scraped_at: str
    race_count: int
    races: list[RaceOdds]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScrapeOutput":
        return cls(
            scraped_at=d["scrapedAt"],
            race_count=d["raceCount"],
            races=[RaceOdds.from_dict(r) for r in d.get("races", [])],
        )


BETFAIR_RENAME = {
    "race_id": "raceId",
    "off_time": "offTime",
    "win_market_url": "winMarketUrl",
    "market_name": "marketName",
    "market_scraped_at": "marketScrapedAt",
    "selection_id": "selectionId",
    "scraped_at": "scrapedAt",
    "race_count": "raceCount",
}


def write_betfair_json(out: ScrapeOutput, path: Path | str) -> None:
    write_json(out, BETFAIR_RENAME, path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_betfair_models.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/models.py tests/test_betfair_models.py
git commit -m "betfair_scraper.models: dataclasses + serialize + from_dict"
```

---

## Task 2: `betfair_scraper/responses.py` — parsers + request-body builders (TDD)

Oracle: `BetfairResponses.kt`. Cross-check cases against `BetfairResponsesTest.kt`.

**Files:**
- Create: `src/betfair_scraper/responses.py`
- Test: `tests/test_betfair_responses.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_betfair_responses.py`:
```python
"""Tests for betfair_scraper.responses."""

from __future__ import annotations

import json

import pytest

from common.markettype import MarketType  # noqa: F401 (parity import)
from betfair_scraper.responses import (
    MarketBookStatus,
    build_book_body,
    build_catalogue_body,
    build_login_body,
    lay_prices_from_book,
    parse_ssoid,
    race_from_catalogue,
)


class TestParseSsoid:
    def test_success(self):
        assert parse_ssoid('{"status":"SUCCESS","token":"abc123"}') == "abc123"

    def test_restricted_mentions_2fa(self):
        with pytest.raises(RuntimeError, match="2FA"):
            parse_ssoid('{"status":"LOGIN_RESTRICTED"}')

    def test_other_failure(self):
        with pytest.raises(RuntimeError, match="status=FAIL"):
            parse_ssoid('{"status":"FAIL"}')

    def test_success_without_token(self):
        with pytest.raises(RuntimeError, match="no token"):
            parse_ssoid('{"status":"SUCCESS"}')

    def test_malformed(self):
        with pytest.raises(RuntimeError, match="not a valid JSON object"):
            parse_ssoid("{not json")


class TestRaceFromCatalogue:
    def test_full(self):
        obj = {
            "marketId": "1.258528220",
            "marketStartTime": "2026-05-25T17:05:00Z",
            "event": {"venue": "Ballinrobe", "countryCode": "IE"},
        }
        race = race_from_catalogue(obj)
        assert race.race_id == "1.258528220"
        assert race.venue == "Ballinrobe"
        assert race.country == "IE"
        assert race.off_time == "2026-05-25T18:05:00+01:00"
        assert race.win_market_url.endswith("/market/1.258528220")

    def test_missing_venue_returns_none(self):
        obj = {"marketId": "1.1", "marketStartTime": "2026-05-25T17:05:00Z",
               "event": {"countryCode": "IE"}}
        assert race_from_catalogue(obj) is None

    def test_bad_start_time_returns_none(self):
        obj = {"marketId": "1.1", "marketStartTime": "nope",
               "event": {"venue": "X", "countryCode": "IE"}}
        assert race_from_catalogue(obj) is None


class TestLayPricesFromBook:
    def test_open_with_lays(self):
        obj = {
            "status": "OPEN",
            "runners": [
                {"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}, {"price": 3.0}]}},
                {"selectionId": 2, "ex": {"availableToLay": []}},
            ],
        }
        snap = lay_prices_from_book(obj)
        assert snap.status is MarketBookStatus.OPEN
        assert snap.lay_by_selection_id == {1: 2.5, 2: None}

    def test_non_open_is_empty(self):
        snap = lay_prices_from_book({"status": "SUSPENDED", "runners": []})
        assert snap.status is MarketBookStatus.OTHER
        assert snap.lay_by_selection_id == {}


class TestBuildBodies:
    def test_login_body_urlencoded(self):
        assert build_login_body("a b", "p&q") == "username=a+b&password=p%26q"

    def test_catalogue_body_pins_horse_racing(self):
        body = json.loads(build_catalogue_body(
            market_type_codes=["WIN"], countries=["GB", "IE"],
            from_="2026-05-25T23:00:00Z", to="2026-05-26T23:00:00Z",
            projection=["EVENT"], max_results=1000, sort="FIRST_TO_START"))
        assert body["filter"]["eventTypeIds"] == ["7"]
        assert body["filter"]["marketTypeCodes"] == ["WIN"]
        assert body["filter"]["marketCountries"] == ["GB", "IE"]
        assert body["filter"]["marketStartTime"] == {
            "from": "2026-05-25T23:00:00Z", "to": "2026-05-26T23:00:00Z"}
        assert body["maxResults"] == "1000"
        assert body["sort"] == "FIRST_TO_START"

    def test_book_body(self):
        body = json.loads(build_book_body(["1.1", "1.2"]))
        assert body["marketIds"] == ["1.1", "1.2"]
        assert body["priceProjection"] == {"priceData": ["EX_BEST_OFFERS"]}

    def test_book_body_rejects_empty(self):
        with pytest.raises(ValueError, match="1..40"):
            build_book_body([])

    def test_book_body_rejects_over_40(self):
        with pytest.raises(ValueError, match="1..40"):
            build_book_body([f"1.{i}" for i in range(41)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_betfair_responses.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/responses.py`**

```python
"""Pure parsers for Betfair responses + request-body builders. No I/O.

Port of BetfairResponses.kt. Login/state errors raise RuntimeError
(mirrors the Kotlin IllegalStateException)."""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from common.timeutil import utc_to_london
from .models import Race


class MarketBookStatus(enum.Enum):
    OPEN = "OPEN"
    OTHER = "OTHER"


@dataclass(frozen=True)
class MarketBookSnapshot:
    status: MarketBookStatus
    # selectionId → best lay price; value is None when availableToLay is empty.
    lay_by_selection_id: dict[int, float | None]


def parse_ssoid(text: str) -> str:
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise RuntimeError(f"login response is not a valid JSON object: {e}")
    status = root.get("status")
    if not isinstance(status, str):
        status = "UNKNOWN"
    if status != "SUCCESS":
        hint = (
            " — this likely means 2FA is enabled on the account. 2FA must be "
            "disabled for interactive login, or switch to cert-based login."
            if status == "LOGIN_RESTRICTED" else ""
        )
        raise RuntimeError(f"login failed with status={status}{hint}")
    token = root.get("token")
    if not isinstance(token, str):
        raise RuntimeError("login response has SUCCESS status but no token")
    return token


def race_from_catalogue(root: dict) -> "Race | None":
    market_id = root.get("marketId")
    start_utc = root.get("marketStartTime")
    event = root.get("event")
    if not isinstance(market_id, str) or not isinstance(start_utc, str) \
            or not isinstance(event, dict):
        return None
    venue = event.get("venue")
    country = event.get("countryCode")
    if not isinstance(venue, str) or not isinstance(country, str):
        return None
    off_time = utc_to_london(start_utc)
    if off_time is None:
        return None
    return Race(
        race_id=market_id,
        venue=venue,
        country=country,
        off_time=off_time,
        win_market_url=(
            "https://www.betfair.com/exchange/plus/horse-racing/market/"
            f"{market_id}"
        ),
    )


def lay_prices_from_book(root: dict) -> MarketBookSnapshot:
    status = (
        MarketBookStatus.OPEN if root.get("status") == "OPEN"
        else MarketBookStatus.OTHER
    )
    if status is not MarketBookStatus.OPEN:
        return MarketBookSnapshot(status, {})
    runners = root.get("runners")
    if not isinstance(runners, list):
        return MarketBookSnapshot(status, {})
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
                    first_price = el.get("price")
                    break
        out[sel] = first_price
    return MarketBookSnapshot(status, out)


def build_login_body(username: str, password: str) -> str:
    return urlencode({"username": username, "password": password})


def build_catalogue_body(
    *, market_type_codes, countries, from_, to, projection, max_results, sort
) -> str:
    return json.dumps({
        "filter": {
            "eventTypeIds": ["7"],
            "marketTypeCodes": list(market_type_codes),
            "marketCountries": list(countries),
            "marketStartTime": {"from": from_, "to": to},
        },
        "marketProjection": list(projection),
        "maxResults": str(max_results),
        "sort": sort,
    })


def build_book_body(market_ids) -> str:
    market_ids = list(market_ids)
    if not (1 <= len(market_ids) <= 40):
        raise ValueError(
            f"build_book_body: marketIds size must be 1..40 (got {len(market_ids)})"
        )
    return json.dumps({
        "marketIds": market_ids,
        "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
    })
```

> `urlencode` produces `username=a+b&password=p%26q` (space→`+`, `&`→`%26`), matching Kotlin's `URLEncoder.encode`. The catalogue/book builders use compact `json.dumps` (no spaces is fine — body is sent over the wire, not asserted on formatting).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_betfair_responses.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/responses.py tests/test_betfair_responses.py
git commit -m "betfair_scraper.responses: parsers + request-body builders"
```

---

## Task 3: `betfair_scraper/classifier.py` — Top-N market classifier (TDD)

Oracle: `MarketClassifier.kt`; cases from `MarketClassifierTest.kt`.

**Files:**
- Create: `src/betfair_scraper/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_classifier.py`:
```python
"""Tests for betfair_scraper.classifier."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.classifier import classify_top_n


def test_ui_name_form():
    assert classify_top_n("Top 3 Finish", None) is MarketType.TOP_3


def test_api_name_form():
    assert classify_top_n("3 TBP", None) is MarketType.TOP_3


def test_case_insensitive_and_trimmed():
    assert classify_top_n("  top 2 FINISH  ", None) is MarketType.TOP_2


def test_to_be_placed_rejected():
    assert classify_top_n("To Be Placed", None) is None


def test_winners_mismatch_rejected():
    assert classify_top_n("Top 3 Finish", 4) is None


def test_winners_match_accepted():
    assert classify_top_n("Top 3 Finish", 3) is MarketType.TOP_3


def test_out_of_range_name():
    assert classify_top_n("Top 6 Finish", None) is None
    assert classify_top_n("1 TBP", None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_classifier.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/classifier.py`**

```python
"""Classify a Betfair market name into a TOP_N MarketType. Port of
MarketClassifier.kt. Accepts the UI form 'Top N Finish' and the REST API
form 'N TBP', N in 2..5."""

from __future__ import annotations

import re

from common.markettype import MarketType

_UI = re.compile(r"top ([2-5]) finish", re.IGNORECASE)
_API = re.compile(r"([2-5]) tbp", re.IGNORECASE)


def classify_top_n(name: str, number_of_winners: "int | None") -> "MarketType | None":
    trimmed = name.strip()
    m = _UI.fullmatch(trimmed) or _API.fullmatch(trimmed)
    if m is None:
        return None
    n = int(m.group(1))
    if number_of_winners is not None and number_of_winners != n:
        return None
    return {2: MarketType.TOP_2, 3: MarketType.TOP_3,
            4: MarketType.TOP_4, 5: MarketType.TOP_5}.get(n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_classifier.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/classifier.py tests/test_classifier.py
git commit -m "betfair_scraper.classifier: Top-N market classifier"
```

---

## Task 4: `betfair_scraper/pivot.py` — per-runner pivot (TDD)

Oracle: `RunnerPivot.kt`; cases from `RunnerPivotTest.kt`.

**Files:**
- Create: `src/betfair_scraper/pivot.py`
- Test: `tests/test_pivot.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_pivot.py`:
```python
"""Tests for betfair_scraper.pivot."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.models import MarketScrape, RunnerEntry
from betfair_scraper.pivot import pivot_market_scrapes


def _scrape(t, runners):
    return MarketScrape(type=t, scraped_at="2026-05-25T17:00:00Z", runners=runners)


def test_win_absent_returns_empty():
    scrapes = {MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(1, "A", 1.5)])}
    assert pivot_market_scrapes(scrapes, "1.1") == []


def test_lay_keys_match_scraped_markets_in_order():
    scrapes = {
        MarketType.WIN: _scrape(MarketType.WIN, [RunnerEntry(1, "A", 2.0), RunnerEntry(2, "B", 3.0)]),
        MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(1, "A", 1.5)]),
    }
    out = pivot_market_scrapes(scrapes, "1.1")
    assert [r.name for r in out] == ["A", "B"]
    assert list(out[0].lay.keys()) == [MarketType.WIN, MarketType.TOP_2]
    # B not in TOP_2 → None for that key
    assert out[1].lay == {MarketType.WIN: 3.0, MarketType.TOP_2: None}
    assert out[0].selection_id == 1


def test_phantom_horse_warns(capsys):
    scrapes = {
        MarketType.WIN: _scrape(MarketType.WIN, [RunnerEntry(1, "A", 2.0)]),
        MarketType.TOP_2: _scrape(MarketType.TOP_2, [RunnerEntry(9, "Ghost", 1.1)]),
    }
    out = pivot_market_scrapes(scrapes, "1.42")
    assert [r.name for r in out] == ["A"]  # Ghost dropped (not in WIN)
    assert "Phantom horse 'Ghost' in TOP_2 for race 1.42" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pivot.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/pivot.py`**

```python
"""Pivot per-market scrapes into per-runner lay maps. Port of RunnerPivot.kt.

WIN absent → []. Each runner's lay map has exactly the keys present in
`scrapes` (declared MarketType order). A runner missing from a scraped
market maps that key to None. Runners in a Top-N but not WIN are dropped
with a stderr warning."""

from __future__ import annotations

import sys

from common.markettype import MarketType
from .models import MarketScrape, RunnerOdds


def pivot_market_scrapes(
    scrapes: dict[MarketType, MarketScrape], race_id_for_warnings: str
) -> list[RunnerOdds]:
    win = scrapes.get(MarketType.WIN)
    if win is None:
        return []

    win_names = {r.name for r in win.runners}
    ordered = [t for t in MarketType if t in scrapes]

    for t in ordered:
        if t is MarketType.WIN:
            continue
        for entry in scrapes[t].runners:
            if entry.name not in win_names:
                print(
                    f"Phantom horse '{entry.name}' in {t.name} for race "
                    f"{race_id_for_warnings} — dropping",
                    file=sys.stderr,
                )

    out: list[RunnerOdds] = []
    for win_entry in win.runners:
        lay: dict[MarketType, float | None] = {}
        for t in ordered:
            entry = next(
                (r for r in scrapes[t].runners if r.name == win_entry.name), None
            )
            lay[t] = entry.lay if entry is not None else None
        out.append(
            RunnerOdds(name=win_entry.name, lay=lay, selection_id=win_entry.selection_id)
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pivot.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/pivot.py tests/test_pivot.py
git commit -m "betfair_scraper.pivot: per-runner lay-map pivot"
```

---

## Task 5: `betfair_scraper/assembly.py` — market-name format + race assembler (TDD)

Oracle: `RaceOddsAssembly.kt`; cases from `RaceOddsAssemblyTest.kt`.

**Files:**
- Create: `src/betfair_scraper/assembly.py`
- Test: `tests/test_assembly.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_assembly.py`:
```python
"""Tests for betfair_scraper.assembly."""

from __future__ import annotations

from common.markettype import MarketType
from betfair_scraper.assembly import assemble_race_odds, format_market_name
from betfair_scraper.models import MarketScrape, Race, RunnerEntry


def _race():
    return Race("1.1", "Ballinrobe", "IE", "2026-05-25T18:05:00+01:00",
                "https://x/market/1.1")


def test_format_with_race_type():
    assert format_market_name(_race(), "2m1f Beg Chs") == "18:05 Ballinrobe - 2m1f Beg Chs"


def test_format_without_race_type():
    assert format_market_name(_race(), "  ") == "18:05 Ballinrobe"


def test_assemble_requires_win():
    scrapes = {MarketType.TOP_2: MarketScrape(MarketType.TOP_2, "2026-05-25T17:00:00Z", [])}
    assert assemble_race_odds(_race(), "name", scrapes) is None


def test_assemble_builds_race_odds():
    scrapes = {
        MarketType.WIN: MarketScrape(MarketType.WIN, "2026-05-25T17:00:00Z",
                                     [RunnerEntry(1, "A", 2.0)]),
    }
    odds = assemble_race_odds(_race(), "18:05 Ballinrobe", scrapes)
    assert odds.race_id == "1.1"
    assert list(odds.market_scraped_at.keys()) == [MarketType.WIN]
    assert odds.runners[0].name == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_assembly.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/assembly.py`**

```python
"""Market-name formatting + race assembly. Port of RaceOddsAssembly.kt."""

from __future__ import annotations

from datetime import datetime

from common.markettype import MarketType
from .models import MarketScrape, Race, RaceOdds
from .pivot import pivot_market_scrapes


def format_market_name(race: Race, race_type: str) -> str:
    """'<HH:mm> <venue> - <raceType>', or '<HH:mm> <venue>' if no type."""
    time = datetime.fromisoformat(race.off_time.replace("Z", "+00:00")).strftime("%H:%M")
    trimmed = race_type.strip()
    return f"{time} {race.venue}" if not trimmed else f"{time} {race.venue} - {trimmed}"


def assemble_race_odds(
    race: Race, market_name: str, scrapes: dict[MarketType, MarketScrape]
) -> "RaceOdds | None":
    """Returns None when the WIN scrape is absent (spec rule 7)."""
    if MarketType.WIN not in scrapes:
        return None
    ordered = [t for t in MarketType if t in scrapes]
    market_scraped_at = {t: scrapes[t].scraped_at for t in ordered}
    runners = pivot_market_scrapes(scrapes, race_id_for_warnings=race.race_id)
    return RaceOdds(
        race_id=race.race_id,
        venue=race.venue,
        country=race.country,
        off_time=race.off_time,
        win_market_url=race.win_market_url,
        market_name=market_name,
        market_scraped_at=market_scraped_at,
        runners=runners,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_assembly.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/assembly.py tests/test_assembly.py
git commit -m "betfair_scraper.assembly: market-name format + race assembler"
```

---

## Task 6: `betfair_scraper/credentials.py` — credentials load + warn (TDD)

Oracle: `Credentials.kt`; cases from `CredentialsTest.kt`.

**Files:**
- Create: `src/betfair_scraper/credentials.py`
- Test: `tests/test_credentials.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_credentials.py`:
```python
"""Tests for betfair_scraper.credentials."""

from __future__ import annotations

import os

import pytest

from betfair_scraper.credentials import (
    Credentials,
    load_credentials,
    parse_credentials,
)


class TestParse:
    def test_happy(self):
        c = parse_credentials('{"username":"u","password":"p","appKey":"k"}')
        assert c == Credentials("u", "p", "k")

    def test_ignores_extra_fields(self):
        c = parse_credentials('{"username":"u","password":"p","appKey":"k","x":1}')
        assert c.app_key == "k"

    def test_missing_fields_listed(self):
        with pytest.raises(ValueError, match="password,appKey"):
            parse_credentials('{"username":"u"}')

    def test_not_object(self):
        with pytest.raises(ValueError, match="not a valid object"):
            parse_credentials("[]")


class TestLoad:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            load_credentials(tmp_path / "nope.json")

    def test_loads_and_warns_when_world_readable(self, tmp_path, capsys):
        p = tmp_path / "credentials.json"
        p.write_text('{"username":"u","password":"p","appKey":"k"}')
        os.chmod(p, 0o644)
        c = load_credentials(p)
        assert c == Credentials("u", "p", "k")
        assert "chmod 600" in capsys.readouterr().err

    def test_no_warn_when_0600(self, tmp_path, capsys):
        p = tmp_path / "credentials.json"
        p.write_text('{"username":"u","password":"p","appKey":"k"}')
        os.chmod(p, 0o600)
        load_credentials(p)
        assert "chmod 600" not in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_credentials.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/credentials.py`**

```python
"""Load and validate ~/.horsey-scraper/credentials.json. Port of Credentials.kt."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    app_key: str


def parse_credentials(text: str) -> Credentials:
    """JSON object with string fields username, password, appKey. Extra
    fields ignored. Missing/non-string fields → ValueError listing all."""
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise ValueError(f"credentials JSON is not a valid object: {e}")
    missing: list[str] = []

    def s(key: str) -> "str | None":
        v = root.get(key)
        if not isinstance(v, str):
            missing.append(key)
            return None
        return v

    username, password, app_key = s("username"), s("password"), s("appKey")
    if missing:
        raise ValueError(
            f"credentials JSON missing or non-string fields: {','.join(missing)}"
        )
    return Credentials(username, password, app_key)


def default_credentials_path() -> Path:
    return Path.home() / ".horsey-scraper" / "credentials.json"


def load_credentials(path: Path | str) -> Credentials:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"credentials file not found: {path}")
    _warn_if_world_readable(path)
    try:
        text = path.read_text()
    except OSError as e:
        raise ValueError(f"failed to read {path}: {e}")
    return parse_credentials(text)


def _warn_if_world_readable(path: Path) -> None:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if mode & 0o077:
        print(
            f"Warning: {path} is readable by group/others; recommend `chmod 600`.",
            file=sys.stderr,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_credentials.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/credentials.py tests/test_credentials.py
git commit -m "betfair_scraper.credentials: load + world-readable warning"
```

---

## Task 7: `betfair_scraper/race_list.py` — day window + WIN catalogue fetch (TDD)

Oracle: `RaceListFetcher.kt`; cases from `RaceListFetcherTest.kt`.

**Files:**
- Create: `src/betfair_scraper/race_list.py`
- Test: `tests/test_race_list.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_race_list.py`:
```python
"""Tests for betfair_scraper.race_list."""

from __future__ import annotations

import json
from datetime import date

from betfair_scraper.race_list import (
    RaceListFetcher,
    london_day_window_utc,
    parse_catalogue_races,
)


class TestLondonDayWindowUtc:
    def test_bst(self):
        # May → BST (+01:00): day starts 23:00Z the previous date.
        assert london_day_window_utc(date(2026, 5, 11)) == (
            "2026-05-10T23:00:00Z", "2026-05-11T23:00:00Z")

    def test_gmt(self):
        assert london_day_window_utc(date(2026, 1, 15)) == (
            "2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z")


def _cat(*entries) -> str:
    return json.dumps(list(entries))


def _entry(market_id, start_utc, venue, country):
    return {"marketId": market_id, "marketStartTime": start_utc,
            "event": {"venue": venue, "countryCode": country}}


class TestParseCatalogueRaces:
    def test_dedupe_and_sort(self):
        text = _cat(
            _entry("1.2", "2026-05-25T18:00:00Z", "Zborough", "GB"),
            _entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"),
            _entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"),  # dup
        )
        races = parse_catalogue_races(text)
        assert [r.race_id for r in races] == ["1.1", "1.2"]  # sorted by offTime

    def test_skips_unparseable(self):
        text = _cat(
            {"marketId": "1.1"},  # missing fields
            _entry("1.2", "2026-05-25T18:00:00Z", "Ascot", "GB"),
        )
        assert [r.race_id for r in parse_catalogue_races(text)] == ["1.2"]


class FakeClient:
    def __init__(self, catalogue_response: str):
        self.catalogue_response = catalogue_response
        self.last_body = None

    def list_market_catalogue(self, body: str) -> str:
        self.last_body = body
        return self.catalogue_response

    def list_market_book(self, body: str) -> str:  # unused here
        raise AssertionError("not called")


class TestRaceListFetcher:
    def test_fetch_uses_win_and_countries(self):
        resp = _cat(_entry("1.1", "2026-05-25T17:00:00Z", "Ascot", "GB"))
        client = FakeClient(resp)
        races = RaceListFetcher(client).fetch(
            frozenset({"gb-ie"}), today=date(2026, 5, 25))
        assert [r.race_id for r in races] == ["1.1"]
        body = json.loads(client.last_body)
        assert body["filter"]["marketTypeCodes"] == ["WIN"]
        assert body["filter"]["marketCountries"] == ["GB", "IE"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_race_list.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/race_list.py`**

```python
"""Today's WIN markets in the selected regions. Port of RaceListFetcher.kt."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from common.regions import countries_for_all
from common.timeutil import LONDON, iso_utc
from .models import Race
from .responses import build_catalogue_body, race_from_catalogue


def london_day_window_utc(day: date) -> tuple[str, str]:
    """(from_utc, to_utc) ISO-'Z' strings for the 24h London day on `day`."""
    start = datetime.combine(day, time(0, 0), tzinfo=LONDON)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=LONDON)
    return iso_utc(start), iso_utc(end)


def parse_catalogue_races(text: str) -> list[Race]:
    """Shred a listMarketCatalogue array into Races. Skips unparseable
    entries, dedupes by raceId (first wins), sorts by (offTime, venue)."""
    arr = json.loads(text)
    out: list[Race] = []
    seen: set[str] = set()
    for el in arr:
        if not isinstance(el, dict):
            continue
        race = race_from_catalogue(el)
        if race is None or race.race_id in seen:
            continue
        seen.add(race.race_id)
        out.append(race)
    out.sort(key=lambda r: (r.off_time, r.venue))
    return out


class RaceListFetcher:
    def __init__(self, client):
        self.client = client

    def fetch(self, regions: frozenset[str], today: "date | None" = None) -> list[Race]:
        if today is None:
            today = datetime.now(LONDON).date()
        from_, to = london_day_window_utc(today)
        countries = sorted(countries_for_all(regions))
        body = build_catalogue_body(
            market_type_codes=["WIN"],
            countries=countries,
            from_=from_,
            to=to,
            projection=["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
            max_results=1000,
            sort="FIRST_TO_START",
        )
        return parse_catalogue_races(self.client.list_market_catalogue(body))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_race_list.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/race_list.py tests/test_race_list.py
git commit -m "betfair_scraper.race_list: day window + WIN catalogue fetch"
```

---

## Task 8: `betfair_scraper/race_odds.py` — PLACE binding, batching, join (TDD)

Oracle: `RaceOddsFetcher.kt`; cases from `RaceOddsFetcherTest.kt`. This is the densest module — port the pure helpers first, then the fetcher.

**Files:**
- Create: `src/betfair_scraper/race_odds.py`
- Test: `tests/test_race_odds.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_race_odds.py`:
```python
"""Tests for betfair_scraper.race_odds."""

from __future__ import annotations

import json

from common.markettype import MarketType
from betfair_scraper.models import Race
from betfair_scraper.race_odds import (
    PlaceMarketEntry,
    RaceOddsFetcher,
    chunk_of_40,
    join_scrapes,
    parse_book_snapshots,
    parse_catalogue_place_markets,
    parse_win_catalogue_runners,
    parse_win_race_keys,
    parse_win_race_types,
    place_markets_by_race_id,
)
from betfair_scraper.responses import MarketBookSnapshot, MarketBookStatus


def test_chunk_of_40():
    assert chunk_of_40([]) == []
    assert chunk_of_40(list(range(41))) == [list(range(40)), [40]]


def test_parse_catalogue_place_markets_filters_and_binds():
    text = json.dumps([
        {  # a Top-2 market that classifies
            "marketName": "2 TBP",
            "marketId": "9.1",
            "description": {"marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [{"selectionId": 1, "runnerName": "A"}],
        },
        {  # To Be Placed → rejected by classifier
            "marketName": "To Be Placed",
            "marketId": "9.2",
            "description": {"marketTime": "2026-05-25T17:00:00Z"},
            "event": {"id": "30.1"},
            "runners": [],
        },
    ])
    entries = parse_catalogue_place_markets(text)
    assert len(entries) == 1
    assert entries[0].market_id == "9.1"
    assert entries[0].type is MarketType.TOP_2
    assert entries[0].event_id == "30.1"
    assert entries[0].runners == {1: "A"}


def test_place_markets_by_race_id_binds_via_event_and_time():
    entry = PlaceMarketEntry("9.1", MarketType.TOP_2, "30.1",
                             "2026-05-25T17:00:00Z", {1: "A"})
    race_key = {"1.1": ("30.1", "2026-05-25T17:00:00Z")}
    out = place_markets_by_race_id([entry], race_key)
    assert out == {"1.1": [entry]}


def test_parse_win_helpers():
    text = json.dumps([{
        "marketId": "1.1", "marketName": "2m1f Beg Chs",
        "marketStartTime": "2026-05-25T17:00:00Z",
        "event": {"id": "30.1"},
        "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    assert parse_win_catalogue_runners(text) == {"1.1": [(1, "A")]}
    assert parse_win_race_types(text) == {"1.1": "2m1f Beg Chs"}
    assert parse_win_race_keys(text) == {"1.1": ("30.1", "2026-05-25T17:00:00Z")}


def test_join_scrapes_drops_non_open_win():
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    snapshots = {"1.1": MarketBookSnapshot(MarketBookStatus.OTHER, {})}
    out = join_scrapes(races, {}, snapshots, {"1.1": [(1, "A")]}, "name",
                       "2026-05-25T17:00:00Z")
    assert out == []


def test_join_scrapes_builds_win_plus_topn():
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    snapshots = {
        "1.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 2.5}),
        "9.1": MarketBookSnapshot(MarketBookStatus.OPEN, {1: 1.4}),
    }
    place = {"1.1": [PlaceMarketEntry("9.1", MarketType.TOP_2, "30.1",
                                      "2026-05-25T17:00:00Z", {1: "A"})]}
    out = join_scrapes(races, place, snapshots, {"1.1": [(1, "A")]}, "name",
                       "2026-05-25T17:00:00Z")
    assert len(out) == 1
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_2: 1.4}


# --- fetcher end-to-end with a fake client driven by a per-body response map ---

class FakeClient:
    """Returns catalogue responses by marketTypeCodes, book responses by call."""
    def __init__(self, win_json, place_json, book_json):
        self.win_json, self.place_json, self.book_json = win_json, place_json, book_json
        self.book_calls = 0

    def list_market_catalogue(self, body: str) -> str:
        codes = json.loads(body)["filter"]["marketTypeCodes"]
        return self.win_json if codes == ["WIN"] else self.place_json

    def list_market_book(self, body: str) -> str:
        self.book_calls += 1
        return self.book_json


def test_fetcher_end_to_end():
    win_json = json.dumps([{
        "marketId": "1.1", "marketName": "2m Hcap",
        "marketStartTime": "2026-05-25T17:00:00Z", "event": {"id": "30.1"},
        "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    place_json = json.dumps([{
        "marketName": "2 TBP", "marketId": "9.1",
        "description": {"marketTime": "2026-05-25T17:00:00Z"},
        "event": {"id": "30.1"}, "runners": [{"selectionId": 1, "runnerName": "A"}],
    }])
    book_json = json.dumps([
        {"marketId": "1.1", "status": "OPEN",
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}]},
        {"marketId": "9.1", "status": "OPEN",
         "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 1.4}]}}]},
    ])
    client = FakeClient(win_json, place_json, book_json)
    races = [Race("1.1", "Ascot", "GB", "2026-05-25T18:00:00+01:00", "u")]
    out = RaceOddsFetcher(
        client, now=lambda: __import__("datetime").datetime(
            2026, 5, 25, 17, 0, tzinfo=__import__("datetime").timezone.utc)
    ).fetch(races, frozenset({"gb-ie"}))
    assert len(out) == 1
    assert out[0].market_name.startswith("18:00 Ascot")
    assert out[0].runners[0].lay == {MarketType.WIN: 2.5, MarketType.TOP_2: 1.4}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/race_odds.py`**

```python
"""Fetch WIN + classified Top-N markets and join into RaceOdds.
Port of RaceOddsFetcher.kt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from common.markettype import MarketType
from common.regions import countries_for_all
from common.timeutil import LONDON, iso_utc
from .assembly import assemble_race_odds, format_market_name
from .classifier import classify_top_n
from .models import MarketScrape, Race, RaceOdds, RunnerEntry
from .race_list import london_day_window_utc
from .responses import (
    MarketBookSnapshot,
    MarketBookStatus,
    build_book_body,
    build_catalogue_body,
    lay_prices_from_book,
)


@dataclass(frozen=True)
class PlaceMarketEntry:
    market_id: str
    type: MarketType
    event_id: str
    market_time: str
    runners: dict[int, str]


def chunk_of_40(items: list) -> list[list]:
    return [items[i:i + 40] for i in range(0, len(items), 40)] if items else []


def _runner_map(catalogue: dict) -> dict[int, str]:
    runners = catalogue.get("runners")
    out: dict[int, str] = {}
    if not isinstance(runners, list):
        return out
    for r in runners:
        if not isinstance(r, dict):
            continue
        sel, name = r.get("selectionId"), r.get("runnerName")
        if isinstance(sel, int) and not isinstance(sel, bool) and isinstance(name, str):
            out[sel] = name
    return out


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


def place_markets_by_race_id(
    entries: list[PlaceMarketEntry],
    race_key_by_race_id: dict[str, tuple[str, str]],
) -> dict[str, list[PlaceMarketEntry]]:
    race_id_by_key = {key: rid for rid, key in race_key_by_race_id.items()}
    out: dict[str, list[PlaceMarketEntry]] = {}
    for entry in entries:
        rid = race_id_by_key.get((entry.event_id, entry.market_time))
        if rid is None:
            continue
        out.setdefault(rid, []).append(entry)
    return out


def parse_win_catalogue_runners(text: str) -> dict[str, list[tuple[int, str]]]:
    arr = json.loads(text)
    out: dict[str, list[tuple[int, str]]] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        market_id = el.get("marketId")
        runners = el.get("runners")
        if not isinstance(market_id, str) or not isinstance(runners, list):
            continue
        pairs: list[tuple[int, str]] = []
        for r in runners:
            if not isinstance(r, dict):
                continue
            sel, name = r.get("selectionId"), r.get("runnerName")
            if isinstance(sel, int) and not isinstance(sel, bool) and isinstance(name, str):
                pairs.append((sel, name))
        out[market_id] = pairs
    return out


def parse_book_snapshots(text: str) -> dict[str, MarketBookSnapshot]:
    arr = json.loads(text)
    out: dict[str, MarketBookSnapshot] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        market_id = el.get("marketId")
        if isinstance(market_id, str):
            out[market_id] = lay_prices_from_book(el)
    return out


def parse_win_race_types(text: str) -> dict[str, str]:
    arr = json.loads(text)
    out: dict[str, str] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        mid = el.get("marketId")
        if isinstance(mid, str):
            name = el.get("marketName")
            out[mid] = name if isinstance(name, str) else ""
    return out


def parse_win_race_keys(text: str) -> dict[str, tuple[str, str]]:
    arr = json.loads(text)
    out: dict[str, tuple[str, str]] = {}
    for el in arr:
        if not isinstance(el, dict):
            continue
        mid = el.get("marketId")
        event = el.get("event")
        if not isinstance(mid, str) or not isinstance(event, dict):
            continue
        eid = event.get("id")
        mst = el.get("marketStartTime")
        if isinstance(eid, str) and isinstance(mst, str):
            out[mid] = (eid, mst)
    return out


def join_scrapes(
    races: list[Race],
    place_markets: dict[str, list[PlaceMarketEntry]],
    snapshots: dict[str, MarketBookSnapshot],
    win_runners: dict[str, list[tuple[int, str]]],
    win_market_name: str,
    scraped_at: str,
) -> list[RaceOdds]:
    out: list[RaceOdds] = []
    for race in races:
        win_snap = snapshots.get(race.race_id)
        if win_snap is None or win_snap.status is not MarketBookStatus.OPEN:
            continue
        name_order = win_runners.get(race.race_id)
        if name_order is None:
            continue
        scrapes: dict[MarketType, MarketScrape] = {
            MarketType.WIN: MarketScrape(
                type=MarketType.WIN,
                scraped_at=scraped_at,
                runners=[
                    RunnerEntry(selection_id=sel, name=name,
                                lay=win_snap.lay_by_selection_id.get(sel))
                    for sel, name in name_order
                ],
            )
        }
        for place in place_markets.get(race.race_id, []):
            snap = snapshots.get(place.market_id)
            if snap is None or snap.status is not MarketBookStatus.OPEN:
                continue
            scrapes[place.type] = MarketScrape(
                type=place.type,
                scraped_at=scraped_at,
                runners=[
                    RunnerEntry(selection_id=sel, name=name,
                                lay=snap.lay_by_selection_id.get(sel))
                    for sel, name in place.runners.items()
                ],
            )
        odds = assemble_race_odds(race, win_market_name, scrapes)
        if odds is not None:
            out.append(odds)
    return out


class RaceOddsFetcher:
    def __init__(self, client, now=None):
        self.client = client
        self._now = now

    def _now_utc(self) -> datetime:
        if self._now is not None:
            return self._now()
        from datetime import timezone
        return datetime.now(timezone.utc)

    def fetch(self, races: list[Race], regions: frozenset[str]) -> list[RaceOdds]:
        if not races:
            return []
        countries = sorted(countries_for_all(regions))
        from_, to = london_day_window_utc(datetime.now(LONDON).date())

        place_json = self.client.list_market_catalogue(build_catalogue_body(
            market_type_codes=["PLACE", "OTHER_PLACE"], countries=countries,
            from_=from_, to=to,
            projection=["EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"],
            max_results=1000, sort="FIRST_TO_START"))
        place_entries = parse_catalogue_place_markets(place_json)

        win_json = self.client.list_market_catalogue(build_catalogue_body(
            market_type_codes=["WIN"], countries=countries, from_=from_, to=to,
            projection=["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION",
                        "RUNNER_DESCRIPTION"],
            max_results=1000, sort="FIRST_TO_START"))
        win_runners = parse_win_catalogue_runners(win_json)
        win_race_types = parse_win_race_types(win_json)
        race_keys = parse_win_race_keys(win_json)

        place_by_race = place_markets_by_race_id(place_entries, race_keys)

        all_ids = list(dict.fromkeys(
            [r.race_id for r in races]
            + [pm.market_id for lst in place_by_race.values() for pm in lst]))
        snapshots: dict[str, MarketBookSnapshot] = {}
        for chunk in chunk_of_40(all_ids):
            snapshots.update(parse_book_snapshots(
                self.client.list_market_book(build_book_body(chunk))))

        scraped_at = iso_utc(self._now_utc())

        out: list[RaceOdds] = []
        for race in races:
            market_name = format_market_name(race, win_race_types.get(race.race_id, ""))
            out.extend(join_scrapes(
                races=[race],
                place_markets={race.race_id: place_by_race.get(race.race_id, [])},
                snapshots=snapshots, win_runners=win_runners,
                win_market_name=market_name, scraped_at=scraped_at))
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_race_odds.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/race_odds.py tests/test_race_odds.py
git commit -m "betfair_scraper.race_odds: PLACE binding, batching, join"
```

---

## Task 9: `betfair_scraper/validation.py` — schema validator (TDD)

Oracle: `SchemaValidator.kt`; cases from `SchemaValidatorTest.kt`.

**Files:**
- Create: `src/betfair_scraper/validation.py`
- Test: `tests/test_betfair_validation.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_betfair_validation.py`:
```python
"""Tests for betfair_scraper.validation."""

from __future__ import annotations

import json

from betfair_scraper.validation import validate_scrape_output


def _valid() -> dict:
    return {
        "scrapedAt": "2026-05-25T17:05:56.890289Z",
        "raceCount": 1,
        "races": [{
            "raceId": "1.258528220", "venue": "Ballinrobe", "country": "IE",
            "offTime": "2026-05-25T18:05:00+01:00",
            "winMarketUrl": "https://x/market/1.258528220",
            "marketName": "18:05 Ballinrobe",
            "marketScrapedAt": {"WIN": "2026-05-25T17:05:58.303431Z"},
            "runners": [
                {"name": "A", "lay": {"WIN": 2.5}, "selectionId": 1},
                {"name": "B", "lay": {"WIN": None}, "selectionId": None},
            ],
        }],
    }


def _v(p: dict) -> list[str]:
    return validate_scrape_output(json.dumps(p))


def test_valid():
    assert _v(_valid()) == []


def test_not_json():
    errs = validate_scrape_output("{bad")
    assert errs and "not valid JSON" in errs[0]


def test_race_count_mismatch():
    p = _valid(); p["raceCount"] = 9
    assert any("raceCount" in e for e in _v(p))


def test_bad_race_id():
    p = _valid(); p["races"][0]["raceId"] = "2.999"
    assert any("raceId does not match" in e for e in _v(p))


def test_bad_country():
    p = _valid(); p["races"][0]["country"] = "FR"
    assert any("country not in" in e for e in _v(p))


def test_bad_offtime():
    p = _valid(); p["races"][0]["offTime"] = "2026-05-25T18:05:00"
    assert any("offTime not ISO-8601 with offset" in e for e in _v(p))


def test_missing_win_key():
    p = _valid()
    p["races"][0]["marketScrapedAt"] = {"TOP_2": "2026-05-25T17:05:58.303431Z"}
    p["races"][0]["runners"] = [{"name": "A", "lay": {"TOP_2": 1.5}, "selectionId": 1}]
    assert any("missing required WIN key" in e for e in _v(p))


def test_unknown_market():
    p = _valid()
    p["races"][0]["marketScrapedAt"]["TOP_9"] = "2026-05-25T17:05:58.303431Z"
    assert any("unknown market" in e for e in _v(p))


def test_lay_key_parity_violation():
    p = _valid()
    p["races"][0]["runners"][0]["lay"] = {"WIN": 2.5, "TOP_2": 1.5}
    assert any("key parity violation" in e for e in _v(p))


def test_selection_id_not_number():
    p = _valid(); p["races"][0]["runners"][0]["selectionId"] = "1"
    assert any("selectionId: not a number" in e for e in _v(p))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_betfair_validation.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/validation.py`**

```python
"""Validate a betfair.json payload string. Port of SchemaValidator.kt.
Returns [] when valid, else human-readable error strings."""

from __future__ import annotations

import json
import re

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_RACE_ID = re.compile(r"^1\.\d+$")
_ALLOWED_COUNTRIES = {"GB", "IE", "US"}
_ALLOWED_MARKETS = {"WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_scrape_output(text: str) -> list[str]:
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
        _require_str(race, "raceId", errors,
                     lambda v: None if _RACE_ID.match(v)
                     else errors.append(f"{ctx}.raceId does not match ^1\\.\\d+$: '{v}'"))
        _require_str(race, "venue", errors)
        _require_str(race, "country", errors,
                     lambda v: None if v in _ALLOWED_COUNTRIES
                     else errors.append(f"{ctx}.country not in {_ALLOWED_COUNTRIES}: '{v}'"))
        _require_str(race, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(race, "winMarketUrl", errors)
        _require_str(race, "marketName", errors)

        msa = race.get("marketScrapedAt")
        if not isinstance(msa, dict):
            errors.append(f"{ctx}.marketScrapedAt: missing or not object")
            continue
        msa_keys = set(msa.keys())
        if not msa_keys:
            errors.append(f"{ctx}.marketScrapedAt: empty (must contain at least WIN)")
        if "WIN" not in msa_keys:
            errors.append(f"{ctx}.marketScrapedAt: missing required WIN key")
        for key in msa_keys:
            if key not in _ALLOWED_MARKETS:
                errors.append(f"{ctx}.marketScrapedAt: unknown market '{key}'")
            v = msa.get(key)
            if not isinstance(v, str) or not is_iso_utc(v):
                shown = v if isinstance(v, str) else ""
                errors.append(f"{ctx}.marketScrapedAt.{key} not ISO-8601 UTC: '{shown}'")

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
            sel = r.get("selectionId")
            if sel is not None and (not isinstance(sel, (int, float)) or isinstance(sel, bool)):
                errors.append(f"{rctx}.selectionId: not a number (got {sel})")
            lay = r.get("lay")
            if not isinstance(lay, dict):
                errors.append(f"{rctx}.lay: missing or not object")
                continue
            if set(lay.keys()) != msa_keys:
                errors.append(
                    f"{rctx}.lay: key parity violation — has {set(lay.keys())}, "
                    f"marketScrapedAt has {msa_keys}")
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

Run: `uv run pytest tests/test_betfair_validation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/validation.py tests/test_betfair_validation.py
git commit -m "betfair_scraper.validation: schema validator"
```

---

## Task 10: `betfair_scraper/client.py` — urllib REST client + opt-in smoke

Oracle: `BetfairClient.kt`. The HTTP client is exercised by an opt-in integration test (real creds + network); unit coverage of the parsing it depends on lives in Task 2.

**Files:**
- Create: `src/betfair_scraper/client.py`
- Test: `tests/test_betfair_client.py`

- [ ] **Step 1: Write the tests (one unit, one opt-in integration)**

`tests/test_betfair_client.py`:
```python
"""Tests for betfair_scraper.client. The HTTP path is opt-in (real creds)."""

from __future__ import annotations

import os

import pytest

from betfair_scraper.client import BetfairClient


def test_betting_endpoint_requires_login():
    client = BetfairClient("app-key")
    with pytest.raises(RuntimeError, match="must call login"):
        client.list_market_catalogue("{}")


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1",
                    reason="set RUN_INTEGRATION=1 (needs ~/.horsey-scraper/credentials.json)")
def test_live_login_and_catalogue():
    from betfair_scraper.credentials import default_credentials_path, load_credentials
    from betfair_scraper.race_list import RaceListFetcher

    creds = load_credentials(default_credentials_path())
    client = BetfairClient(creds.app_key)
    client.login(creds.username, creds.password)
    races = RaceListFetcher(client).fetch(frozenset({"gb-ie"}))
    assert isinstance(races, list)
```

- [ ] **Step 2: Run the unit test to verify it fails**

Run: `uv run pytest tests/test_betfair_client.py::test_betting_endpoint_requires_login -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/betfair_scraper/client.py`**

```python
"""Thin REST client for the three Betfair endpoints. Port of BetfairClient.kt.
Uses stdlib urllib (no browser, no third-party dep). No retries."""

from __future__ import annotations

import urllib.error
import urllib.request

from .responses import build_login_body, parse_ssoid

LOGIN_URL = "https://identitysso.betfair.com/api/login"
CATALOGUE_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/"
BOOK_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketBook/"


class BetfairClient:
    def __init__(self, app_key: str, *, opener=None):
        self.app_key = app_key
        self._ssoid: "str | None" = None
        self._opener = opener or urllib.request.build_opener()

    def login(self, username: str, password: str) -> None:
        req = urllib.request.Request(
            LOGIN_URL,
            data=build_login_body(username, password).encode(),
            headers={
                "X-Application": self.app_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        self._ssoid = parse_ssoid(self._send(req, timeout=15))

    def list_market_catalogue(self, body: str) -> str:
        return self._send(self._betting_request(CATALOGUE_URL, body), timeout=30)

    def list_market_book(self, body: str) -> str:
        return self._send(self._betting_request(BOOK_URL, body), timeout=30)

    def _betting_request(self, url: str, body: str) -> urllib.request.Request:
        if self._ssoid is None:
            raise RuntimeError("BetfairClient: must call login() before betting endpoints")
        return urllib.request.Request(
            url,
            data=body.encode(),
            headers={
                "X-Application": self.app_key,
                "X-Authentication": self._ssoid,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def _send(self, req: urllib.request.Request, timeout: int) -> str:
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            snippet = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"HTTP {e.code} from {req.full_url}: {snippet}")
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `uv run pytest tests/test_betfair_client.py -q`
Expected: PASS (1 passed, 1 skipped — the integration test).

- [ ] **Step 5: Commit**

```bash
git add src/betfair_scraper/client.py tests/test_betfair_client.py
git commit -m "betfair_scraper.client: urllib REST client + opt-in smoke"
```

---

## Task 11: `betfair_scraper/cli.py` + `__main__.py` + `validate.py` (TDD)

Oracle: `Main.kt` / `ValidateMain.kt`.

**Files:**
- Create: `src/betfair_scraper/cli.py`
- Create: `src/betfair_scraper/__main__.py`
- Create: `src/betfair_scraper/validate.py`
- Test: `tests/test_betfair_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_betfair_cli.py`:
```python
"""Tests for the Betfair CLI orchestration (injected fake client)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from betfair_scraper.cli import main


class FakeClient:
    def __init__(self):
        self.logged_in = False

    def login(self, u, p):
        self.logged_in = True

    def list_market_catalogue(self, body: str) -> str:
        codes = json.loads(body)["filter"]["marketTypeCodes"]
        if codes == ["WIN"]:
            return json.dumps([{
                "marketId": "1.1", "marketName": "2m Hcap",
                "marketStartTime": "2026-05-25T17:00:00Z", "event": {"id": "30.1"},
                "runners": [{"selectionId": 1, "runnerName": "A"}],
            }])
        return json.dumps([])

    def list_market_book(self, body: str) -> str:
        return json.dumps([{
            "marketId": "1.1", "status": "OPEN",
            "runners": [{"selectionId": 1, "ex": {"availableToLay": [{"price": 2.5}]}}],
        }])


def test_happy_path_writes_betfair_json(tmp_path: Path, monkeypatch, capsys):
    # Avoid touching the real credentials file:
    import betfair_scraper.cli as cli
    monkeypatch.setattr(cli, "load_credentials", lambda _p: cli_creds())
    out = tmp_path / "betfair.json"
    rc = main(
        ["gb-ie"],
        make_client=lambda app_key: FakeClient(),
        now=lambda: datetime(2026, 5, 25, 17, 0, tzinfo=timezone.utc),
        out_path=out,
    )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["raceCount"] == 1
    assert payload["races"][0]["raceId"] == "1.1"
    assert "regions=gb-ie" in capsys.readouterr().out


def cli_creds():
    from betfair_scraper.credentials import Credentials
    return Credentials("u", "p", "k")


def test_bad_region_exits_1(monkeypatch):
    import betfair_scraper.cli as cli
    monkeypatch.setattr(cli, "load_credentials", lambda _p: cli_creds())
    assert main(["xx"], make_client=lambda app_key: FakeClient()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_betfair_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: betfair_scraper.cli`.

- [ ] **Step 3: Implement `src/betfair_scraper/cli.py`**

```python
"""Entry point: one pass over today's racing via the Betfair Exchange API.
Port of Main.kt. Returns process exit code (0 ok, 1 region/scrape error,
2 credentials error)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from common.regions import parse_regions
from common.timeutil import iso_utc
from .client import BetfairClient
from .credentials import default_credentials_path, load_credentials
from .models import ScrapeOutput, write_betfair_json
from .race_list import RaceListFetcher
from .race_odds import RaceOddsFetcher

OUTPUT_FILE = "betfair.json"


def main(argv=None, *, make_client=None, now=None, out_path: Path | str = OUTPUT_FILE) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        regions = parse_regions(argv[0]) if argv else parse_regions("gb-ie")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        creds = load_credentials(default_credentials_path())
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    run_start = (now or (lambda: datetime.now(timezone.utc)))()
    make_client = make_client or (lambda app_key: BetfairClient(app_key))

    print("Horsey Scraper — Betfair Exchange API — multi-market lay")
    print(f"regions={','.join(sorted(regions))}")
    print("=" * 80)

    client = make_client(creds.app_key)
    try:
        client.login(creds.username, creds.password)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"\n[{iso_utc(run_start)}] Fetching today's race list…")
    try:
        races = RaceListFetcher(client).fetch(regions)
    except Exception as e:
        print(f"Error fetching race list: {e}", file=sys.stderr)
        return 1
    print(f"Found {len(races)} races today.")
    for r in races:
        print(f"  {r.off_time}  {r.country}  {r.venue}  ({r.race_id})")

    try:
        results = RaceOddsFetcher(client).fetch(races, regions)
    except Exception as e:
        print(f"Error fetching odds: {e}", file=sys.stderr)
        return 1

    for odds in results:
        markets = ",".join(t.name for t in odds.market_scraped_at)
        print(f"  {odds.off_time} {odds.venue} ({odds.race_id}) → "
              f"{len(odds.runners)} runners, markets=[{markets}]")
    result_ids = {o.race_id for o in results}
    for r in races:
        if r.race_id not in result_ids:
            print(f"  {r.off_time} {r.venue} ({r.race_id}) DROPPED")

    output = ScrapeOutput(
        scraped_at=iso_utc(run_start), race_count=len(results), races=results)
    write_betfair_json(output, out_path)
    print(f"\nWrote {out_path} ({len(results)} races)")
    return 0
```

- [ ] **Step 4: Create `src/betfair_scraper/__main__.py`**

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 5: Create `src/betfair_scraper/validate.py`**

```python
"""Validate a betfair.json file.
Usage: python -m betfair_scraper.validate [betfair.json]
Exit 0 = valid, 1 = errors, 2 = file error."""

from __future__ import annotations

import sys
from pathlib import Path

from .validation import validate_scrape_output


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("betfair.json")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    errors = validate_scrape_output(path.read_text())
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

Run: `uv run pytest tests/test_betfair_cli.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add src/betfair_scraper/cli.py src/betfair_scraper/__main__.py src/betfair_scraper/validate.py tests/test_betfair_cli.py
git commit -m "betfair_scraper: CLI orchestration + __main__ + validate entry"
```

---

## Task 12: Golden round-trip test + cross-check the validator accepts our output (TDD)

Commit a sanitized `betfair.json` sample and assert: (a) it passes the validator, and (b) read→write→read is stable (catches float/int/key-order drift).

**Files:**
- Create: `tests/fixtures/betfair_sample.json`
- Test: `tests/test_betfair_golden.py`

- [ ] **Step 1: Create the fixture `tests/fixtures/betfair_sample.json`**

```json
{
  "scrapedAt": "2026-05-25T17:05:56.890289Z",
  "raceCount": 1,
  "races": [
    {
      "raceId": "1.258528220",
      "venue": "Ballinrobe",
      "country": "IE",
      "offTime": "2026-05-25T18:05:00+01:00",
      "winMarketUrl": "https://www.betfair.com/exchange/plus/horse-racing/market/1.258528220",
      "marketName": "18:05 Ballinrobe - 2m1f Beg Chs",
      "marketScrapedAt": {
        "WIN": "2026-05-25T17:05:58.303431Z",
        "TOP_2": "2026-05-25T17:05:58.303431Z"
      },
      "runners": [
        {
          "name": "Sony Bill",
          "lay": { "WIN": 2.72, "TOP_2": 1.99 },
          "selectionId": 66986352
        },
        {
          "name": "No Offer",
          "lay": { "WIN": null, "TOP_2": null },
          "selectionId": 832048
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_betfair_golden.py`:
```python
"""Golden round-trip: the validator accepts the sample, and
read→write→read is stable (guards float/int/key-order drift)."""

from __future__ import annotations

import json
from pathlib import Path

from betfair_scraper.models import ScrapeOutput, write_betfair_json
from betfair_scraper.validation import validate_scrape_output

FIXTURE = Path(__file__).parent / "fixtures" / "betfair_sample.json"


def test_sample_passes_validator():
    assert validate_scrape_output(FIXTURE.read_text()) == []


def test_round_trip_stable(tmp_path: Path):
    original = json.loads(FIXTURE.read_text())
    out = ScrapeOutput.from_dict(original)
    target = tmp_path / "betfair.json"
    write_betfair_json(out, target)
    reproduced = json.loads(target.read_text())
    assert reproduced == original


def test_selection_id_is_int_after_round_trip(tmp_path: Path):
    out = ScrapeOutput.from_dict(json.loads(FIXTURE.read_text()))
    target = tmp_path / "betfair.json"
    write_betfair_json(out, target)
    sel = json.loads(target.read_text())["races"][0]["runners"][0]["selectionId"]
    assert isinstance(sel, int)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_betfair_golden.py -q`
Expected: PASS (3 tests). If `test_round_trip_stable` fails, inspect the diff — likely a field-order or float-format mismatch in `models.py`/`jsonio.py`; fix there.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — `common` + PaddyPower + all Betfair tests (integration skipped).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/betfair_sample.json tests/test_betfair_golden.py
git commit -m "betfair_scraper: golden round-trip + validator-accepts-output test"
```

---

## Plan 2 self-review checklist

- [ ] `uv run pytest -q` fully green (integration skipped).
- [ ] `python -m betfair_scraper --help`-style smoke: `uv run python -c "import betfair_scraper.cli, betfair_scraper.validate, betfair_scraper.__main__"` imports cleanly.
- [ ] Field/method names consistent: `ScrapeOutput.from_dict`, `write_betfair_json`, `RaceOddsFetcher(client, now=...)`, `RaceListFetcher(client).fetch(regions, today=...)`, `lay_by_selection_id`.
- [ ] `betfair.json` produced by a real run (or the golden fixture) validates and round-trips.
- [ ] Kotlin tree still present (deleted in Plan 3). Proceed to Plan 3 (arb finder + cutover).
