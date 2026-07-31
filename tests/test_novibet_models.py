from novibet_scraper.models import (
    EachWayTerms, NovibetOutput, NovibetRace, NovibetRunner, NovibetStub,
)


def test_round_trips_a_full_payload():
    out = NovibetOutput.from_dict({
        "scrapedAt": "2026-07-31T12:00:00Z",
        "raceCount": 1,
        "races": [{
            "venue": "Wolverhampton",
            "country": "GB",
            "offTime": "2026-07-31T13:00:00+00:00",
            "marketName": "Race Winner",
            "scrapedAt": "2026-07-31T12:00:00Z",
            "eachWayTerms": {"fraction": 0.2, "places": 3},
            "runners": [{"name": "Marianne Mozart",
                         "winPrice": 15.0, "winPriceRaw": "14/1"}],
        }],
    })
    assert out.scraped_at == "2026-07-31T12:00:00Z"
    assert out.race_count == 1
    race = out.races[0]
    assert race.venue == "Wolverhampton"
    assert race.country == "GB"
    assert race.off_time == "2026-07-31T13:00:00+00:00"
    assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)
    assert race.runners[0] == NovibetRunner(
        name="Marianne Mozart", win_price=15.0, win_price_raw="14/1")


def test_missing_each_way_terms_is_none():
    race = NovibetRace.from_dict({
        "venue": "Musselburgh", "country": "GB",
        "offTime": "2026-07-31T17:15:00+00:00", "marketName": "Race Winner",
        "scrapedAt": "2026-07-31T12:00:00Z", "eachWayTerms": None, "runners": [],
    })
    assert race.each_way_terms is None
    assert race.runners == []


def test_runner_prices_may_be_null():
    r = NovibetRunner.from_dict({"name": "Suspended"})
    assert r.win_price is None and r.win_price_raw is None


def test_stub_is_a_plain_record():
    s = NovibetStub(bet_context_id="47383682", venue="Wolverhampton",
                    country="GB", start_time_utc="2026-07-31T13:00:00+00:00")
    assert s.bet_context_id == "47383682"
    assert s.country == "GB"
