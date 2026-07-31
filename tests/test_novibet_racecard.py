"""The each-way terms come from the market category CAPTION.

The sysname (HORSE_RACING_RACE_WINNER_EACHWAY_<places>_<divisor>) is wrong
on Place Boost races — 5 of 30 GB/IRE races on the capture day. Trusting it
inflates the place fraction AND picks the wrong Betfair TOP_N market, both
biased toward reporting arbs that are not there. See
tests/fixtures/novibet_README.md."""

from __future__ import annotations

from novibet_scraper.models import EachWayTerms, NovibetRace
from novibet_scraper.racecard import parse_each_way_caption, parse_racecard
from conftest import mutate  # repo convention: tests/ is not a package

SCRAPED = "2026-07-31T12:00:00Z"


def _parse(payload, venue="Goodwood", country="GB"):
    return parse_racecard(payload, SCRAPED, venue=venue, country=country)


class TestParseEachWayCaption:
    def test_plain_each_way(self):
        assert parse_each_way_caption("E/W 1/5 - 3 Places") == EachWayTerms(0.2, 3)

    def test_quarter_odds_two_places(self):
        assert parse_each_way_caption("E/W 1/4 - 2 Places") == EachWayTerms(0.25, 2)

    def test_place_boost_prefix(self):
        assert parse_each_way_caption("Place Boost 1/5 - 4 Places") == EachWayTerms(0.2, 4)

    def test_singular_place(self):
        assert parse_each_way_caption("E/W 1/4 - 1 Place") == EachWayTerms(0.25, 1)

    def test_unparseable_returns_none(self):
        for bad in ("", "Race Winner", "E/W", "1/5", "Insurebet - 2 Places",
                    "E/W 1/0 - 3 Places"):
            assert parse_each_way_caption(bad) is None, bad


class TestEachWayTermsFollowTheCaption:
    def test_agreeing_sysname(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=3)

    def test_two_places(self, novibet_racecard_2pl):
        race = _parse(novibet_racecard_2pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.25, places=2)

    def test_boost_mismatch_4pl_follows_caption_not_sysname(
            self, novibet_racecard_boost_mismatch_4pl):
        # sysname says 3 places at 1/4; the caption says 4 places at 1/5.
        race = _parse(novibet_racecard_boost_mismatch_4pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=4)

    def test_boost_mismatch_5pl_follows_caption_not_sysname(
            self, novibet_racecard_boost_mismatch_5pl):
        # sysname says 2 places at 1/5; the caption says 5 places at 1/5.
        race = _parse(novibet_racecard_boost_mismatch_5pl,
                      venue="Galway", country="IRE")
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=5)

    def test_six_places_is_parsed_not_dropped(self, novibet_racecard_6pl):
        # arb_finder skips it later (Betfair stops at TOP_5); novibet.json
        # still records the true terms.
        race = _parse(novibet_racecard_6pl)
        assert race.each_way_terms == EachWayTerms(fraction=0.2, places=6)

    def test_no_each_way_market_yields_none(self, novibet_racecard_no_eachway):
        race = _parse(novibet_racecard_no_eachway, venue="Musselburgh")
        assert race.each_way_terms is None
        assert len(race.runners) == 5  # win market is still there

    def test_each_way_pulled_near_off_yields_none(self, novibet_racecard_near_off):
        race = _parse(novibet_racecard_near_off)
        assert race.each_way_terms is None
        assert len(race.runners) == 15

    def test_unparseable_caption_yields_none(self, novibet_racecard_3pl):
        p = mutate(novibet_racecard_3pl)
        cat = next(c for c in p["marketCategories"] if "EACHWAY" in c["sysname"])
        cat["caption"] = "Enhanced Each Way Special"
        race = _parse(p)
        assert race.each_way_terms is None


class TestParseRacecard:
    def test_race_metadata(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        assert isinstance(race, NovibetRace)
        assert race.venue == "Wolverhampton"
        assert race.country == "GB"
        assert race.off_time == "2026-07-31T13:00:00+00:00"
        assert race.market_name == "Race Winner"
        assert race.scraped_at == SCRAPED

    def test_runner_prices(self, novibet_racecard_3pl):
        race = _parse(novibet_racecard_3pl, venue="Wolverhampton")
        by_name = {r.name: r for r in race.runners}
        assert by_name["Marianne Mozart"].win_price == 15.0
        assert by_name["Marianne Mozart"].win_price_raw == "14/1"
        for r in race.runners:
            assert (r.win_price is None) == (r.win_price_raw is None)

    def test_non_runners_are_excluded(self, novibet_racecard_6pl):
        # 22 horses on the card, 4 NonRunner, 18 in the win market.
        race = _parse(novibet_racecard_6pl)
        assert len(race.runners) == 18
        names = {r.name for r in race.runners}
        for nr in ("Beagle Bay", "Cosi Bello", "Mirsky", "Rhoscolyn"):
            assert nr not in names

    def test_unavailable_runner_kept_but_price_nulled(self, novibet_racecard_3pl):
        p = mutate(novibet_racecard_3pl)
        win = next(c for c in p["marketCategories"]
                   if c["sysname"] == "HORSE_RACING_MAIN")
        item = win["items"][0]["betViews"][0]["betItems"][0]
        victim = item["caption"]
        item["isAvailable"] = False
        race = _parse(p, venue="Wolverhampton")
        got = next(r for r in race.runners if r.name == victim)
        assert got.win_price is None and got.win_price_raw is None

    def test_no_markets_yields_none(self, novibet_racecard_no_markets):
        assert _parse(novibet_racecard_no_markets, venue="Fairview",
                      country="SAF") is None

    def test_missing_or_malformed_payload_yields_none(self):
        assert _parse({}) is None
        assert _parse({"marketCategories": []}) is None
        assert _parse({"startDateTime": "2026-07-31T13:00:00+00:00",
                       "marketCategories": []}) is None
