"""Validate a betfair.json payload string. Port of SchemaValidator.kt.
Returns [] when valid, else human-readable error strings."""

from __future__ import annotations

import json
import re

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_RACE_ID = re.compile(r"^1\.\d+$")
_ALLOWED_COUNTRIES = {"GB", "IE", "US"}
_ALLOWED_MARKETS = {"WIN", "TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_scrape_output(text: str) -> list[str]:
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
        _require_str(race, "raceId", errors,
                     lambda v: None if _RACE_ID.fullmatch(v)
                     else errors.append(f"{ctx}.raceId does not match ^1\\.\\d+$: '{v}'"))
        _require_str(race, "venue", errors)
        _require_str(race, "country", errors,
                     lambda v: None if v in _ALLOWED_COUNTRIES
                     else errors.append(f"{ctx}.country not in {_ALLOWED_COUNTRIES}: '{v}'"))
        _require_str(race, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(race, "winMarketUrl", errors)
        _require_str(race, "marketName", errors)

        msa = race.get("marketScrapedAt")
        if not isinstance(msa, dict):
            errors.append(f"{ctx}.marketScrapedAt: missing or not object")
            continue
        msa_keys = set(msa.keys())
        if not msa_keys:
            errors.append(f"{ctx}.marketScrapedAt: empty (must contain at least WIN)")
        if "WIN" not in msa_keys:
            errors.append(f"{ctx}.marketScrapedAt: missing required WIN key")
        for key in msa_keys:
            if key not in _ALLOWED_MARKETS:
                errors.append(f"{ctx}.marketScrapedAt: unknown market '{key}'")
            v = msa.get(key)
            if not isinstance(v, str) or not is_iso_utc(v):
                shown = v if isinstance(v, str) else ""
                errors.append(f"{ctx}.marketScrapedAt.{key} not ISO-8601 UTC: '{shown}'")

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
            sel = r.get("selectionId")
            if sel is not None and (not isinstance(sel, (int, float)) or isinstance(sel, bool)):
                errors.append(f"{rctx}.selectionId: not a number (got {sel})")
            lay = r.get("lay")
            if not isinstance(lay, dict):
                errors.append(f"{rctx}.lay: missing or not object")
                continue
            if set(lay.keys()) != msa_keys:
                errors.append(
                    f"{rctx}.lay: key parity violation — has {set(lay.keys())}, "
                    f"marketScrapedAt has {msa_keys}")
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
