"""Market-name formatting + race assembly. Port of RaceOddsAssembly.kt."""

from __future__ import annotations

from datetime import datetime

from common.markettype import MarketType
from .models import MarketScrape, Race, RaceOdds
from .pivot import pivot_market_scrapes


def format_market_name(race: Race, race_type: str) -> str:
    """'<HH:mm> <venue> - <raceType>', or '<HH:mm> <venue>' if no type."""
    time = datetime.fromisoformat(race.off_time.replace("Z", "+00:00")).strftime("%H:%M")
    trimmed = race_type.strip()
    return f"{time} {race.venue}" if not trimmed else f"{time} {race.venue} - {trimmed}"


def assemble_race_odds(
    race: Race, market_name: str, scrapes: dict[MarketType, MarketScrape]
) -> "RaceOdds | None":
    """Returns None when the WIN scrape is absent (spec rule 7)."""
    if MarketType.WIN not in scrapes:
        return None
    ordered = [t for t in MarketType if t in scrapes]
    market_scraped_at = {t: scrapes[t].scraped_at for t in ordered}
    runners = pivot_market_scrapes(scrapes, race_id_for_warnings=race.race_id)
    return RaceOdds(
        race_id=race.race_id,
        venue=race.venue,
        country=race.country,
        off_time=race.off_time,
        win_market_url=race.win_market_url,
        market_name=market_name,
        market_scraped_at=market_scraped_at,
        runners=runners,
    )
