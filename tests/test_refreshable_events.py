"""Tests for refreshable event card selection."""

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.db.events import get_refreshable_event_cards  # noqa: E402


class RefreshableEventsFilterTest(unittest.IsolatedAsyncioTestCase):
    async def test_filters_past_and_keeps_future(self):
        now = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        past = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=2)).isoformat()
        period_end = (now + timedelta(days=10)).isoformat()

        samples = [
            {"id": 1, "status": "active", "message_id": 10, "date_time": past, "period_end": ""},
            {"id": 2, "status": "active", "message_id": 11, "date_time": future, "period_end": ""},
            {"id": 3, "status": "active", "message_id": 12, "date_time": past, "period_end": period_end},
            {"id": 4, "status": "active", "message_id": 0, "date_time": future, "period_end": ""},
            {"id": 5, "status": "cancelled", "message_id": 13, "date_time": future, "period_end": ""},
        ]

        # Patch get_active_events used inside get_refreshable_event_cards
        import bot.db.events as events_mod

        async def fake_active():
            return [e for e in samples if e["status"] == "active"]

        original = events_mod.get_active_events
        events_mod.get_active_events = fake_active
        try:
            result = await get_refreshable_event_cards(now=now)
        finally:
            events_mod.get_active_events = original

        ids = {int(e["id"]) for e in result}
        self.assertEqual(ids, {2, 3})


if __name__ == "__main__":
    unittest.main()
