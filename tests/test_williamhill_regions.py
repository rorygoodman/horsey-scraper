from williamhill_scraper.regions import filters_for_all


def test_gb_ie_maps_to_uk_ireland():
    assert filters_for_all(frozenset({"gb-ie"})) == {"uk-ireland"}


def test_us_maps_to_us_canada():
    assert filters_for_all(frozenset({"us"})) == {"us-canada"}


def test_union():
    assert filters_for_all(frozenset({"gb-ie", "us"})) == {"uk-ireland", "us-canada"}
