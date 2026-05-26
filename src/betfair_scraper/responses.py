"""Pure parsers for Betfair responses + request-body builders. No I/O.

Port of BetfairResponses.kt. Login/state errors raise RuntimeError
(mirrors the Kotlin IllegalStateException)."""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from urllib.parse import urlencode

from common.timeutil import utc_to_london
from .models import Race


class MarketBookStatus(enum.Enum):
    OPEN = "OPEN"
    OTHER = "OTHER"


@dataclass(frozen=True)
class MarketBookSnapshot:
    status: MarketBookStatus
    # selectionId → best lay price; value is None when availableToLay is empty.
    lay_by_selection_id: dict[int, float | None]


def parse_ssoid(text: str) -> str:
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise RuntimeError(f"login response is not a valid JSON object: {e}")
    status = root.get("status")
    if not isinstance(status, str):
        status = "UNKNOWN"
    if status != "SUCCESS":
        hint = (
            " — this likely means 2FA is enabled on the account. 2FA must be "
            "disabled for interactive login, or switch to cert-based login."
            if status == "LOGIN_RESTRICTED" else ""
        )
        raise RuntimeError(f"login failed with status={status}{hint}")
    token = root.get("token")
    if not isinstance(token, str):
        raise RuntimeError("login response has SUCCESS status but no token")
    return token


def race_from_catalogue(root: dict) -> "Race | None":
    market_id = root.get("marketId")
    start_utc = root.get("marketStartTime")
    event = root.get("event")
    if not isinstance(market_id, str) or not isinstance(start_utc, str) \
            or not isinstance(event, dict):
        return None
    venue = event.get("venue")
    country = event.get("countryCode")
    if not isinstance(venue, str) or not isinstance(country, str):
        return None
    off_time = utc_to_london(start_utc)
    if off_time is None:
        return None
    return Race(
        race_id=market_id,
        venue=venue,
        country=country,
        off_time=off_time,
        win_market_url=(
            "https://www.betfair.com/exchange/plus/horse-racing/market/"
            f"{market_id}"
        ),
    )


def lay_prices_from_book(root: dict) -> MarketBookSnapshot:
    status = (
        MarketBookStatus.OPEN if root.get("status") == "OPEN"
        else MarketBookStatus.OTHER
    )
    if status is not MarketBookStatus.OPEN:
        return MarketBookSnapshot(status, {})
    runners = root.get("runners")
    if not isinstance(runners, list):
        return MarketBookSnapshot(status, {})
    out: dict[int, float | None] = {}
    for r in runners:
        if not isinstance(r, dict):
            continue
        sel = r.get("selectionId")
        if not isinstance(sel, int) or isinstance(sel, bool):
            continue
        ex = r.get("ex")
        lays = ex.get("availableToLay") if isinstance(ex, dict) else None
        first_price = None
        if isinstance(lays, list):
            for el in lays:
                if isinstance(el, dict):
                    # First offer's price; keep only if numeric (Kotlin used
                    # .asDouble). Non-numeric/bool/null → leave as None.
                    p = el.get("price")
                    if isinstance(p, (int, float)) and not isinstance(p, bool):
                        first_price = p
                    break
        out[sel] = first_price
    return MarketBookSnapshot(status, out)


def build_login_body(username: str, password: str) -> str:
    return urlencode({"username": username, "password": password})


def build_catalogue_body(
    *, market_type_codes, countries, from_, to, projection, max_results, sort
) -> str:
    return json.dumps({
        "filter": {
            "eventTypeIds": ["7"],
            "marketTypeCodes": list(market_type_codes),
            "marketCountries": list(countries),
            "marketStartTime": {"from": from_, "to": to},
        },
        "marketProjection": list(projection),
        "maxResults": str(max_results),
        "sort": sort,
    })


def build_book_body(market_ids) -> str:
    market_ids = list(market_ids)
    if not (1 <= len(market_ids) <= 40):
        raise ValueError(
            f"build_book_body: marketIds size must be 1..40 (got {len(market_ids)})"
        )
    return json.dumps({
        "marketIds": market_ids,
        "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
    })
