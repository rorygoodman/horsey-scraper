"""Validate an arbs.json payload string. Port of ArbSchemaValidator.kt."""

from __future__ import annotations

import json

from common.isovalid import is_iso_offset_datetime, is_iso_utc

_EW_PLACES = range(2, 6)  # 2..5 inclusive
_ALLOWED_TOP_N = {"TOP_2", "TOP_3", "TOP_4", "TOP_5"}


def validate_arbs_output(text: str) -> list[str]:
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
    arb_count = _require_int(root, "arbCount", errors)
    arbs = root.get("arbs")
    if not isinstance(arbs, list):
        errors.append("arbs: missing or not array")
        return errors
    if arb_count is not None and arb_count != len(arbs):
        errors.append(f"arbCount ({arb_count}) != arbs.length ({len(arbs)})")

    for i, arb in enumerate(arbs):
        ctx = f"arbs[{i}]"
        if not isinstance(arb, dict):
            errors.append(f"{ctx}: not an object")
            continue
        _require_str(arb, "venue", errors)
        _require_str(arb, "country", errors)
        _require_str(arb, "offTime", errors,
                     lambda v: None if is_iso_offset_datetime(v)
                     else errors.append(f"{ctx}.offTime not ISO-8601 with offset: '{v}'"))
        _require_str(arb, "marketName", errors)
        _require_str(arb, "betfairWinMarketId", errors)

        margin = arb.get("margin")
        if not isinstance(margin, (int, float)) or isinstance(margin, bool):
            errors.append(f"{ctx}.margin: missing or not a number")
        elif margin <= 0.0:
            errors.append(f"{ctx}.margin must be > 0, got {margin}")

        runner = arb.get("runner")
        if not isinstance(runner, dict):
            errors.append(f"{ctx}.runner: missing or not an object")
        else:
            _require_str(runner, "name", errors)
            sel = runner.get("selectionId")
            if not isinstance(sel, (int, float)) or isinstance(sel, bool):
                errors.append(f"{ctx}.runner.selectionId: missing or not a number")

        _validate_paddy_leg(arb.get("paddypower"), f"{ctx}.paddypower", errors)
        _validate_betfair_leg(arb.get("betfair"), f"{ctx}.betfair", errors)
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
    for key in ("winLay", "topNLay"):
        v = el.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errors.append(f"{ctx}.{key}: missing or not a number")
    top_n = el.get("topNType")
    if not isinstance(top_n, str):
        errors.append(f"{ctx}.topNType: missing or not a string")
    elif top_n not in _ALLOWED_TOP_N:
        errors.append(f"{ctx}.topNType: '{top_n}' not in {_ALLOWED_TOP_N}")


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
