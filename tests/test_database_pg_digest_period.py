import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bot import database_pg
from bot.utils.helpers import build_event_message_link


class DatabasePgDigestPeriodTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_events_for_digest_filters_by_period(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        fake_rows = [
            database_pg._CompatRow(
                {
                    "id": 1,
                    "title": "Soon",
                    "date_time": soon,
                    "status": "active",
                    "category": "food",
                }
            ),
            database_pg._CompatRow(
                {
                    "id": 2,
                    "title": "Far future",
                    "date_time": far,
                    "status": "active",
                    "category": "food",
                }
            ),
        ]

        async def fake_run_query(query, parameters=None):
            if "FROM participants" in query:
                return [database_pg._CompatResultSet([])]
            return [database_pg._CompatResultSet(fake_rows)]

        with patch("bot.database_pg._run_query", side_effect=fake_run_query):
            events = await database_pg.get_events_for_digest(period="week")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], 1)

    async def test_get_events_for_digest_includes_active_period_event(self):
        started = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        period_end = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
        fake_rows = [
            database_pg._CompatRow(
                {
                    "id": 3,
                    "title": "Ongoing period",
                    "date_time": started,
                    "period_end": period_end,
                    "status": "active",
                    "category": "sport",
                }
            ),
        ]

        async def fake_run_query(query, parameters=None):
            if "FROM participants" in query:
                return [database_pg._CompatResultSet([])]
            return [database_pg._CompatResultSet(fake_rows)]

        with patch("bot.database_pg._run_query", side_effect=fake_run_query):
            events = await database_pg.get_events_for_digest(period="all")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], 3)


class BuildEventMessageLinkTests(unittest.TestCase):
    def test_main_chat_link(self):
        link = build_event_message_link(-1001234567890, 42)
        self.assertEqual(link, "https://t.me/c/1234567890/42")

    def test_forum_topic_link(self):
        link = build_event_message_link(-1001234567890, 99, thread_id=7)
        self.assertEqual(link, "https://t.me/c/1234567890/7/99")


if __name__ == "__main__":
    unittest.main()
