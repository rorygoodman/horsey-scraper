"""Validate a horses.json payload string."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(2, 6)  # 2..5 inclusive
_ALLOWED_PLACE_MARKETS = {"TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_horses_output(text: str) -> list[str]:
    errors: list[str] = []
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        return [f"not valid JSON object: {e}"]

    for key in ("computedAt", "betfairScrapedAt", "paddypowerScrapedAt"):
        _require_str(root, key, errors,
                     lambda v, k=key: None if is_iso_utc(v)
                     else errors.append(f"{k} is not ISO-8601 UTC instant: '{v}'"))
    horse_count = _require_int(root, "horseCount", errors)
    horses = root.get("horses")
    if not isinstance(horses, list):
        errors.append("horses: missing or not array")
        return errors
    if horse_count is not None and horse_count != len(horses):
        errors.append(f"horseCount ({horse_count}) != horses.length ({len(horses)})")

    for i, h in enumerate(horses):
        ctx = f"horses[{i}]"
        if not isinstance(h, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(h, "venue", errors)
        _require_str(h, "country", errors)
        _require_str(h, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(h, "marketName", errors)
        _require_str(h, "betfairWinMarketId", errors)

        edge = h.get("edge")
        if not isinstance(edge, (int, float)) or isinstance(edge, bool):
            errors.append(f"{ctx}.edge: missing or not a number")

        runner = h.get("runner")
        if not isinstance(runner, dict):
            errors.append(f"{ctx}.runner: missing or not an object")
        else:
            _require_str(runner, "name", errors)
            sel = runner.get("selectionId")
            if not isinstance(sel, (int, float)) or isinstance(sel, bool):
                errors.append(f"{ctx}.runner.selectionId: missing or not a number")

        _validate_paddy_leg(h.get("paddypower"), f"{ctx}.paddypower", errors)
        _validate_betfair_leg(h.get("betfair"), f"{ctx}.betfair", errors)
    return errors


def _validate_paddy_leg(el, ctx: str, errors: list[str]) -> None:
    if not isinstance(el, dict):
        errors.append(f"{ctx}: missing or not an object")
        return
    wp = el.get("winPrice")
    if not isinstance(wp, (int, float)) or isinstance(wp, bool):
        errors.append(f"{ctx}.winPrice: missing or not a number")
    _require_str(el, "winPriceRaw", errors)
    ew = el.get("eachWayTerms")
    if not isinstance(ew, dict):
        errors.append(f"{ctx}.eachWayTerms: missing or not an object")
        return
    frac = ew.get("fraction")
    if not isinstance(frac, (int, float)) or isinstance(frac, bool) \
            or not (0.0 < float(frac) <= 1.0):
        errors.append(f"{ctx}.eachWayTerms.fraction must be in (0,1], got {frac}")
    places = ew.get("places")
    if not isinstance(places, int) or isinstance(places, bool) or places not in _EW_PLACES:
        errors.append(f"{ctx}.eachWayTerms.places must be in {_EW_PLACES}, got {places}")


def _validate_betfair_leg(el, ctx: str, errors: list[str]) -> None:
    if not isinstance(el, dict):
        errors.append(f"{ctx}: missing or not an object")
        return
    for key in ("winLay", "placeLay"):
        v = el.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errors.append(f"{ctx}.{key}: missing or not a number")
    pm = el.get("placeMarket")
    if not isinstance(pm, str):
        errors.append(f"{ctx}.placeMarket: missing or not a string")
    elif pm not in _ALLOWED_PLACE_MARKETS:
        errors.append(f"{ctx}.placeMarket: '{pm}' not in {_ALLOWED_PLACE_MARKETS}")


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
