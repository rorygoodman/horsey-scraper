import json

from common.markettype import MarketType
from sport888_scraper.models import EachWayTerms
from arb_finder.models import (
    BetfairLayLeg,
    Horse888,
    Horses888Output,
    Runner,
    Sport888PriceLeg,
    write_horses888_json,
)


def _out() -> Horses888Output:
    return Horses888Output(
        computed_at="2026-07-22T12:01:00Z",
        betfair_scraped_at="2026-07-22T12:00:00Z",
        sport888_scraped_at="2026-07-22T12:00:30Z",
        horse_count=1,
        horses=[Horse888(
            venue="Worcester", country="GB",
            off_time="2026-07-22T13:55:00+01:00", market_name="12:55 Worcester",
            betfair_win_market_id="1.234",
            runner=Runner(name="Holy Legend", selection_id=99),
            sport888=Sport888PriceLeg(3.25, "9/4", EachWayTerms(0.2, 3)),
            betfair=BetfairLayLeg(win_lay=3.4, place_lay=1.5,
                                  place_market=MarketType.TOP_3),
            edge=0.05,
        )],
    )


def test_writes_camelcase_888_leg(tmp_path):
    p = tmp_path / "888horses.json"
    write_horses888_json(_out(), p)
    data = json.loads(p.read_text())
    assert data["sport888ScrapedAt"] == "2026-07-22T12:00:30Z"
    h = data["horses"][0]
    assert h["betfairWinMarketId"] == "1.234"
    assert h["runner"]["selectionId"] == 99
    assert h["sport888"]["winPrice"] == 3.25
    assert h["sport888"]["winPriceRaw"] == "9/4"
    assert h["sport888"]["eachWayTerms"] == {"fraction": 0.2, "places": 3}
    assert h["betfair"]["placeMarket"] == "TOP_3"
    # semantically correct: no "paddypower" key in the 888 output
    assert "paddypower" not in json.dumps(data)
