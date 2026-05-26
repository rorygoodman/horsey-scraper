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
