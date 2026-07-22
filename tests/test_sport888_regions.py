from common.regions import parse_regions
from sport888_scraper.regions import REGION_SLUGS, slugs_for_all


def test_gb_ie_maps_to_uk_and_ireland():
    assert slugs_for_all(parse_regions("gb-ie")) == frozenset({"uk-and-ireland"})


def test_us_maps_to_north_america():
    assert slugs_for_all(parse_regions("us")) == frozenset({"north-america"})


def test_both_regions_union():
    assert slugs_for_all(parse_regions("gb-ie,us")) == frozenset(
        {"uk-and-ireland", "north-america"}
    )


def test_map_keys_match_region_ids():
    assert set(REGION_SLUGS) == {"gb-ie", "us"}
