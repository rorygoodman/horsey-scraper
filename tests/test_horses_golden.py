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
