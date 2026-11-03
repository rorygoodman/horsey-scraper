from williamhill_scraper.times import to_iso_utc


def test_colonless_offset_with_millis():
    assert to_iso_utc("2026-11-03T15:48:00.000+0000") == "2026-11-03T15:48:00Z"


def test_non_utc_offset_is_converted():
    assert to_iso_utc("2026-07-31T14:00:00.000+0100") == "2026-07-31T13:00:00Z"


def test_already_iso_forms_pass_through():
    assert to_iso_utc("2026-11-03T15:48:00Z") == "2026-11-03T15:48:00Z"
    assert to_iso_utc("2026-11-03T15:48:00+00:00") == "2026-11-03T15:48:00Z"


def test_unparseable_is_none():
    for bad in (None, "", "15:48", "not a date", 1793533515):
        assert to_iso_utc(bad) is None, bad
