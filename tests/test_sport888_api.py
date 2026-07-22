from sport888_scraper import api


def test_schedule_url_is_today_tab():
    assert api.SCHEDULE_URL.endswith("getSchedule/horse-racing?tab=today")
    assert api.SCHEDULE_URL.startswith("https://spectate-web.888sport.com/")


def test_racecard_url_embeds_event_id():
    url = api.racecard_url("7960079")
    assert url == (
        "https://spectate-web.888sport.com/spectate/sportsbook-req/"
        "getRacecard/7960079"
    )


def test_warmup_url_is_888sport():
    assert api.WARMUP_URL.startswith("https://www.888sport.com/")
