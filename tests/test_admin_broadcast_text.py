import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")

admin = importlib.import_module("bot.handlers.admin")


class AdminBroadcastTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_afisha_includes_iphone_hint_when_links_present(self):
        events = [
            {
                "id": 1,
                "title": "Поход",
                "date_time": "2026-07-01T12:00:00+03:00",
                "location": "Парк",
                "message_id": 100,
                "thread_id": 7,
            }
        ]
        with patch(
            "bot.handlers.admin.get_events_for_digest",
            new=AsyncMock(return_value=events),
        ):
            text = await admin._build_events_broadcast_text("all")

        self.assertIn("iPhone", text)
        self.assertIn("Избранное", text)
        self.assertIn("открыть сообщение", text)

    async def test_afisha_skips_iphone_hint_without_links(self):
        events = [
            {
                "id": 2,
                "title": "Без ссылки",
                "date_time": "2026-07-01T12:00:00+03:00",
                "location": "Парк",
                "message_id": None,
                "thread_id": 0,
            }
        ]
        with patch(
            "bot.handlers.admin.get_events_for_digest",
            new=AsyncMock(return_value=events),
        ):
            text = await admin._build_events_broadcast_text("week")

        self.assertNotIn("Избранное", text)


if __name__ == "__main__":
    unittest.main()
