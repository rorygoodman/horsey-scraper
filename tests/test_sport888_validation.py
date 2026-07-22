import json

from sport888_scraper.models import (
    EachWayTerms,
    Sport888Output,
    Sport888Race,
    Sport888Runner,
)
from sport888_scraper.output import write_sport888_json
from sport888_scraper.validation import validate_sport888_output


def _valid_output() -> Sport888Output:
    return Sport888Output(
        scraped_at="2026-07-22T12:00:00Z", race_count=1,
        races=[Sport888Race(
            venue="Worcester", country="uk-and-ireland",
            off_time="2026-07-22T12:55:00+00:00", market_name="Winner Market",
            scraped_at="2026-07-22T12:00:00Z", each_way_terms=EachWayTerms(0.2, 3),
            runners=[Sport888Runner("Holy Legend", 3.25, "9/4"),
                     Sport888Runner("No Price", None, None)],
        )],
    )


def test_serialized_output_is_valid(tmp_path):
    p = tmp_path / "888sport.json"
    write_sport888_json(_valid_output(), p)
    assert validate_sport888_output(p.read_text()) == []


def test_race_count_mismatch_flagged():
    d = json.loads(_dump(_valid_output()))
    d["raceCount"] = 99
    errs = validate_sport888_output(json.dumps(d))
    assert any("raceCount" in e for e in errs)


def test_price_parity_violation_flagged():
    d = json.loads(_dump(_valid_output()))
    d["races"][0]["runners"][0]["winPriceRaw"] = None  # price set, raw null
    errs = validate_sport888_output(json.dumps(d))
    assert any("parity" in e.lower() for e in errs)


def test_bad_offtime_flagged():
    d = json.loads(_dump(_valid_output()))
    d["races"][0]["offTime"] = "not-a-date"
    errs = validate_sport888_output(json.dumps(d))
    assert any("offTime" in e for e in errs)


def test_not_json():
    assert validate_sport888_output("{not json") != []


def _dump(out: Sport888Output) -> str:
    from common.jsonio import to_camel_dict
    from sport888_scraper.output import SPORT888_RENAME
    return json.dumps(to_camel_dict(out, SPORT888_RENAME))
