from williamhill_scraper import api


def test_day_index_is_todays_all_regions_feed():
    assert api.DAY_INDEX_URL.endswith("/horse-racing/en-gb/region-competitions/all/today")
    assert api.DAY_INDEX_URL.startswith("https://sports.williamhill.com/data/rmp01/")


def test_event_url():
    assert api.event_url("OB_EV41748430").endswith(
        "/horse-racing/en-gb/events/OB_EV41748430")


def test_event_url_escapes():
    assert "/events/a%2Fb" in api.event_url("a/b")
