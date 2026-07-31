"""Shared pytest fixtures and helpers for paddypower-scraper tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


@pytest.fixture
def card63_payload() -> dict:
    """Raw meetings-index response (content-managed-page/v7?cardsToFetch=63)."""
    return _load("card63_meetings.json")


@pytest.fixture
def racing_page_payload() -> dict:
    """Raw per-meeting response (racing-page/v7?raceId=...) for Ballinrobe."""
    return _load("racing_page_meeting.json")


@pytest.fixture
def eight88_schedule_payload() -> dict:
    """Raw 888 getSchedule?tab=today response (trimmed to UK&IRE + N.America)."""
    return _load("eight88_schedule.json")


@pytest.fixture
def eight88_racecard_payload() -> dict:
    """Raw 888 getRacecard response for a GB race (Worcester)."""
    return _load("eight88_racecard.json")


def mutate(payload: dict) -> dict:
    """Deep-copy a fixture so a test can mutate it without affecting others."""
    return copy.deepcopy(payload)


@pytest.fixture
def novibet_overview_payload() -> dict:
    """Raw Novibet day-index response (2 days: Jul 31 + Aug 01, 2026)."""
    return _load("novibet_overview.json")


@pytest.fixture
def novibet_racecard_3pl() -> dict:
    """Wolverhampton 13:00 — 10 runners, E/W 1/5 - 3 Places, sysname agrees."""
    return _load("novibet_racecard_ew_3pl_1_5.json")


@pytest.fixture
def novibet_racecard_2pl() -> dict:
    """Goodwood 13:25 — 7 runners, E/W 1/4 - 2 Places."""
    return _load("novibet_racecard_ew_2pl_1_4.json")


@pytest.fixture
def novibet_racecard_boost_mismatch_4pl() -> dict:
    """Goodwood 14:35 — caption says 4 places 1/5, sysname says 3_4."""
    return _load("novibet_racecard_ew_4pl_1_5_boost_mismatch.json")


@pytest.fixture
def novibet_racecard_boost_mismatch_5pl() -> dict:
    """Galway 17:35 — caption says 5 places 1/5, sysname says 2_5."""
    return _load("novibet_racecard_ew_5pl_1_5_boost_mismatch.json")


@pytest.fixture
def novibet_racecard_6pl() -> dict:
    """Goodwood 14:00 — 6 places (unpriceable), 4 non-runners on the card."""
    return _load("novibet_racecard_ew_6pl_1_5_boost.json")


@pytest.fixture
def novibet_racecard_no_eachway() -> dict:
    """Musselburgh 17:15 — 5-runner field, no each-way market offered."""
    return _load("novibet_racecard_no_eachway.json")


@pytest.fixture
def novibet_racecard_near_off() -> dict:
    """Goodwood 12:50 — 1 min from off; each-way pulled, win market live."""
    return _load("novibet_racecard_near_off.json")


@pytest.fixture
def novibet_racecard_no_markets() -> dict:
    """Fairview at the off — marketCategories is empty."""
    return _load("novibet_racecard_no_markets.json")
