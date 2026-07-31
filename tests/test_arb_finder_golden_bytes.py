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
