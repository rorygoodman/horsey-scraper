"""The bookie registry is the single place JSON key names are declared."""

from __future__ import annotations

from common.markettype import MarketType
from arb_finder.bookies import BOOKIES, PADDYPOWER, SPORT888
from arb_finder.models import (
    BetfairLayLeg, BookieHorsesOutput, BookiePriceLeg, PricedHorse, Runner,
    build_rename, write_bookie_horses_json,
)


class _Terms:
    """Structural stand-in for a scraper's EachWayTerms (fraction/places)."""
    def __init__(self, fraction, places):
        self.fraction = fraction
        self.places = places


def test_registry_is_keyed_by_cli_token():
    assert set(BOOKIES) == {"paddypower", "888"}
    assert BOOKIES["paddypower"] is PADDYPOWER
    assert BOOKIES["888"] is SPORT888


def test_paddypower_declares_its_json_names():
    assert PADDYPOWER.leg_field == "paddypower"
    assert PADDYPOWER.scraped_at_field == "paddypowerScrapedAt"
    assert PADDYPOWER.default_bookie_input == "paddypower.json"
    assert PADDYPOWER.default_output == "horses.json"


def test_sport888_declares_its_json_names():
    assert SPORT888.leg_field == "sport888"
    assert SPORT888.scraped_at_field == "sport888ScrapedAt"
    assert SPORT888.default_bookie_input == "888sport.json"
    assert SPORT888.default_output == "888horses.json"


def test_build_rename_maps_the_two_variable_fields():
    r = build_rename(SPORT888)
    assert r["bookie"] == "sport888"
    assert r["bookie_scraped_at"] == "sport888ScrapedAt"
    # shared entries survive
    assert r["off_time"] == "offTime"
    assert r["win_price_raw"] == "winPriceRaw"


def _output() -> BookieHorsesOutput:
    return BookieHorsesOutput(
        computed_at="2026-07-31T12:00:00Z",
        betfair_scraped_at="2026-07-31T11:59:01Z",
        bookie_scraped_at="2026-07-31T11:59:05Z",
        horse_count=1,
        horses=[PricedHorse(
            venue="Goodwood", country="GB",
            off_time="2026-07-31T14:00:00+01:00", market_name="14:00 Goodwood",
            betfair_win_market_id="1.1",
            runner=Runner("Marianne Mozart", 12345678),
            bookie=BookiePriceLeg(15.0, "14/1", _Terms(0.2, 3)),
            betfair=BetfairLayLeg(16.0, 4.1, MarketType.TOP_3),
            edge=0.81)],
    )


def test_writer_uses_the_bookie_leg_name(tmp_path):
    import json
    target = tmp_path / "out.json"
    write_bookie_horses_json(_output(), PADDYPOWER, target)
    data = json.loads(target.read_text())
    assert "paddypower" in data["horses"][0]
    assert "bookie" not in data["horses"][0]
    assert "paddypowerScrapedAt" in data

    write_bookie_horses_json(_output(), SPORT888, target)
    data = json.loads(target.read_text())
    assert "sport888" in data["horses"][0]
    assert "sport888ScrapedAt" in data


def test_field_order_is_unchanged(tmp_path):
    import json
    target = tmp_path / "out.json"
    write_bookie_horses_json(_output(), PADDYPOWER, target)
    data = json.loads(target.read_text())
    assert list(data.keys()) == [
        "computedAt", "betfairScrapedAt", "paddypowerScrapedAt",
        "horseCount", "horses"]
    assert list(data["horses"][0].keys()) == [
        "venue", "country", "offTime", "marketName", "betfairWinMarketId",
        "runner", "paddypower", "betfair", "edge"]
