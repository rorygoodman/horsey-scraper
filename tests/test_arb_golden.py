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
