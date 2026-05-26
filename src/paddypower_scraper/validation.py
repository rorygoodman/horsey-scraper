"""Validate a paddypower.json payload string against the schema.

Port of PaddySchemaValidator.kt. Returns [] when valid, else a list of
human-readable error strings (one per violation)."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(1, 7)  # 1..6 inclusive (PaddyPower side)


def validate_paddy_output(text: str) -> list[str]:
    errors: list[str] = []
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        return [f"not valid JSON object: {e}"]

    _require_str(root, "scrapedAt", errors,
                 lambda v: None if is_iso_utc(v)
                 else errors.append(f"top-level scrapedAt is not ISO-8601 UTC instant: '{v}'"))
    race_count = _require_int(root, "raceCount", errors)
    races = root.get("races")
    if not isinstance(races, list):
        errors.append("races: missing or not array")
        return errors
    if race_count is not None and race_count != len(races):
        errors.append(f"raceCount ({race_count}) != races.length ({len(races)})")

    for i, race in enumerate(races):
        ctx = f"races[{i}]"
        if not isinstance(race, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(race, "venue", errors)
        _require_str(race, "country", errors)
        _require_str(race, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(race, "marketName", errors)
        _require_str(race, "raceUrl", errors)
        _require_str(race, "scrapedAt", errors,
                     lambda v: None if is_iso_utc(v)
                     else errors.append(f"{ctx}.scrapedAt not ISO-8601 UTC: '{v}'"))

        ew = race.get("eachWayTerms")
        if ew is not None:
            if not isinstance(ew, dict):
                errors.append(f"{ctx}.eachWayTerms: not an object or null")
            else:
                frac = ew.get("fraction")
                if not isinstance(frac, (int, float)) or isinstance(frac, bool) \
                        or not (0.0 < float(frac) <= 1.0):
                    errors.append(f"{ctx}.eachWayTerms.fraction must be in (0,1], got {frac}")
                places = ew.get("places")
                if not isinstance(places, int) or isinstance(places, bool) \
                        or places not in _EW_PLACES:
                    errors.append(f"{ctx}.eachWayTerms.places must be in {_EW_PLACES}, got {places}")

        runners = race.get("runners")
        if not isinstance(runners, list):
            errors.append(f"{ctx}.runners: missing or not array")
            continue
        for j, r in enumerate(runners):
            rctx = f"{ctx}.runners[{j}]"
            if not isinstance(r, dict):
                errors.append(f"{rctx}: not an object")
                continue
            _require_str(r, "name", errors)
            wp = r.get("winPrice")
            raw = r.get("winPriceRaw")
            wp_null = wp is None
            raw_null = raw is None
            if wp_null != raw_null:
                errors.append(
                    f"{rctx}: price parity violation — winPrice null={wp_null}, "
                    f"winPriceRaw null={raw_null}"
                )
            if not wp_null and (not isinstance(wp, (int, float)) or isinstance(wp, bool)):
                errors.append(f"{rctx}.winPrice: not a number")
            if not raw_null and not isinstance(raw, str):
                errors.append(f"{rctx}.winPriceRaw: not a string")
    return errors


def _require_str(obj: dict, key: str, errors: list[str], extra=None) -> "str | None":
    v = obj.get(key)
    if not isinstance(v, str):
        errors.append(f"{key}: missing or not string")
        return None
    if extra is not None:
        extra(v)
    return v


def _require_int(obj: dict, key: str, errors: list[str]) -> "int | None":
    v = obj.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        errors.append(f"{key}: missing or not number")
        return None
    return v
