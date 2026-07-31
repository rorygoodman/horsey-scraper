"""The bookie registry is the single place JSON key names are declared."""

from __future__ import annotations

from dataclasses import dataclass, fields

from common.markettype import MarketType
from arb_finder.bookies import BOOKIES, NOVIBET, PADDYPOWER, SPORT888
from arb_finder.models import (
    _BASE_RENAME, BetfairLayLeg, BookieHorsesOutput, BookiePriceLeg,
    PricedHorse, Runner, build_rename, write_bookie_horses_json,
)


@dataclass(frozen=True)
class _Terms:
    """Stands in for a scraper's EachWayTerms (all three are frozen dataclasses)."""
    fraction: float
    places: int


def test_registry_is_keyed_by_cli_token():
    assert set(BOOKIES) == {"paddypower", "888", "novibet"}
    assert BOOKIES["paddypower"] is PADDYPOWER
    assert BOOKIES["888"] is SPORT888
    assert BOOKIES["novibet"] is NOVIBET


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


def test_novibet_declares_its_json_names():
    assert NOVIBET.leg_field == "novibet"
    assert NOVIBET.scraped_at_field == "novibetScrapedAt"
    assert NOVIBET.default_bookie_input == "novibet.json"
    assert NOVIBET.default_output == "novibethorses.json"


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


def test_bookie_fields_do_not_collide_with_other_output_keys():
    """write_json applies one flat rename map by dataclass field name at
    every level of the output tree. If a future bookie's leg_field or
    scraped_at_field ever matched one of the fixed keys the output already
    emits (venue, country, runner, betfair, edge, offTime, marketName,
    horseCount, ...), the serializer would silently collapse two distinct
    fields into a single JSON key. Every BOOKIES entry must stay clear of
    that fixed key set, and clear of itself (leg_field != scraped_at_field)."""
    variable_field_names = {"bookie", "bookie_scraped_at"}
    fixed_keys: set[str] = set()
    for dc in (BookieHorsesOutput, PricedHorse, Runner, BookiePriceLeg, BetfairLayLeg):
        for f in fields(dc):
            if f.name in variable_field_names:
                continue
            fixed_keys.add(_BASE_RENAME.get(f.name, f.name))
    # EachWayTerms is a structural (non-arb_finder) dataclass nested under
    # eachWayTerms; its own fields pass straight through unrenamed.
    fixed_keys |= {"fraction", "places"}

    for bookie in BOOKIES.values():
        assert bookie.leg_field not in fixed_keys, (
            f"{bookie.key}: leg_field {bookie.leg_field!r} collides with a "
            "fixed output key")
        assert bookie.scraped_at_field not in fixed_keys, (
            f"{bookie.key}: scraped_at_field {bookie.scraped_at_field!r} "
            "collides with a fixed output key")
        assert bookie.leg_field != bookie.scraped_at_field
