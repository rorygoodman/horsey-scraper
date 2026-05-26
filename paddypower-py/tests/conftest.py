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


def mutate(payload: dict) -> dict:
    """Deep-copy a fixture so a test can mutate it without affecting others."""
    return copy.deepcopy(payload)
