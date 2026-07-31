from novibet_scraper import api


def test_warmup_is_the_horse_racing_page():
    assert api.WARMUP_URL == "https://www.novibet.ie/sports/horse-racing/4372612"


def test_overview_url_targets_the_day_index():
    assert api.OVERVIEW_URL.startswith(
        "https://www.novibet.ie/spt/feed/marketviews/horse-racing-overview2/4324/4372612")
    assert "lang=en-IE" in api.OVERVIEW_URL
    assert "usrGrp=IE" in api.OVERVIEW_URL


def test_racecard_url_embeds_the_bet_context_id():
    url = api.racecard_url("47383682")
    assert url.startswith(
        "https://www.novibet.ie/spt/feed/marketviews/horse-racing-race2/4324/47383682")
    assert "lang=en-IE" in url


def test_racecard_url_escapes_its_argument():
    assert "a/b" not in api.racecard_url("a/b")


def test_gateway_headers_are_sent():
    # A bare fetch without the x-gw-* set is rejected by the gateway.
    for key in ("x-gw-domain-key", "x-gw-application-name", "x-gw-country-sysname",
                "x-gw-language-sysname", "x-gw-channel", "x-gw-client-layout",
                "x-gw-cms-key", "x-gw-currency-sysname", "x-gw-client-timezone",
                "x-gw-odds-representation"):
        assert key in api.API_HEADERS, f"missing gateway header {key}"
    assert api.API_HEADERS["accept"].startswith("application/json")
