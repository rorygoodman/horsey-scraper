"""Per-bookie JSON key names and default paths.

One Bookie entry is the only place a bookie's output naming is declared:
the leg field in each horse, the <bookie>ScrapedAt timestamp, and the
default input/output filenames. Adding a bookie means adding an entry
here, not another model or another CLI branch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bookie:
    key: str                   # --source token
    leg_field: str             # JSON key of the bookie price leg
    scraped_at_field: str      # JSON key of the bookie's scrapedAt
    default_bookie_input: str  # default bookie-scrape input file
    default_output: str        # default priced-arb output file


PADDYPOWER = Bookie(
    key="paddypower",
    leg_field="paddypower",
    scraped_at_field="paddypowerScrapedAt",
    default_bookie_input="paddypower.json",
    default_output="horses.json",
)

SPORT888 = Bookie(
    key="888",
    leg_field="sport888",
    scraped_at_field="sport888ScrapedAt",
    default_bookie_input="888sport.json",
    default_output="888horses.json",
)

NOVIBET = Bookie(
    key="novibet",
    leg_field="novibet",
    scraped_at_field="novibetScrapedAt",
    default_bookie_input="novibet.json",
    default_output="novibethorses.json",
)

BOOKIES: dict[str, Bookie] = {b.key: b for b in (PADDYPOWER, SPORT888, NOVIBET)}
