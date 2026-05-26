"""Opt-in integration test: launches real Chromium and hits PaddyPower.

Run with: RUN_INTEGRATION=1 uv run pytest -m integration"""

import os

import pytest

from paddypower_scraper.api import MEETINGS_INDEX_URL
from paddypower_scraper.browser import BrowserSession

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 to run live-network browser tests",
)
class TestBrowserSessionLive:
    def test_fetch_meetings_index_returns_dict_with_attachments(self):
        with BrowserSession() as s:
            data = s.fetch_json(MEETINGS_INDEX_URL)
        assert isinstance(data, dict)
        assert "attachments" in data
        races = data["attachments"].get("races", {})
        assert isinstance(races, dict)
        assert len(races) > 0, "expected at least one race in the meetings index"
