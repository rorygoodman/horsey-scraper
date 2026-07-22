import copy

from sport888_scraper.models import EachWayTerms, Sport888Race
from sport888_scraper.racecard import parse_racecard

SCRAPED = "2026-07-22T12:00:00Z"


class TestParseRacecard:
    def test_parses_worcester(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        assert isinstance(race, Sport888Race)
        assert race.venue == "Worcester"
        assert race.country == "uk-and-ireland"
        assert race.off_time == "2026-07-22T12:55:00+00:00"
        assert race.scraped_at == SCRAPED
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)

    def test_runner_prices(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        by_name = {r.name: r for r in race.runners}
        holy = by_name["Holy Legend"]
        assert holy.win_price == 3.25
        assert holy.win_price_raw == "9/4"
        # every runner obeys price parity
        for r in race.runners:
            assert (r.win_price is None) == (r.win_price_raw is None)

    def test_only_winner_market_runners(self, eight88_racecard_payload):
        race = parse_racecard(eight88_racecard_payload, SCRAPED)
        # 8 winner-market runners in the fixture
        assert len(race.runners) == 8

    def test_no_each_way_when_flag_off(self, eight88_racecard_payload):
        p = copy.deepcopy(eight88_racecard_payload)
        eid = next(iter(p["racecard"]["each_way_terms"]))
        p["racecard"]["each_way_terms"][eid]["allow_each_way"] = "0"
        race = parse_racecard(p, SCRAPED)
        assert race.each_way_terms is None

    def test_returns_none_when_no_events(self):
        assert parse_racecard({"racecard": {"events": {}}}, SCRAPED) is None
        assert parse_racecard({}, SCRAPED) is None

    def test_disqualified_runner_kept_but_nulled(self, eight88_racecard_payload):
        p = copy.deepcopy(eight88_racecard_payload)
        sels = p["racecard"]["selections_details"]
        victim_id = next(k for k, s in sels.items() if s.get("market_id") == "1")
        victim_name = sels[victim_id]["name"]
        sels[victim_id]["betable"] = False  # disqualify: non-betable
        race = parse_racecard(p, SCRAPED)
        names = [r.name for r in race.runners]
        assert victim_name in names, "disqualified runner must still be emitted"
        victim = next(r for r in race.runners if r.name == victim_name)
        assert victim.win_price is None and victim.win_price_raw is None
