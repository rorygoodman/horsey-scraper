from common.regions import parse_regions
from novibet_scraper.regions import REGION_COUNTRIES, countries_for_all


def test_gb_ie_maps_to_novibets_own_captions():
    # Novibet says "IRE", not Betfair's "IE".
    assert REGION_COUNTRIES["gb-ie"] == frozenset({"GB", "IRE"})


def test_us_maps_to_usa():
    assert REGION_COUNTRIES["us"] == frozenset({"USA"})


def test_countries_for_all_unions():
    assert countries_for_all(parse_regions("gb-ie,us")) == frozenset(
        {"GB", "IRE", "USA"})


def test_unknown_region_id_contributes_nothing():
    assert countries_for_all(frozenset({"mars"})) == frozenset()
