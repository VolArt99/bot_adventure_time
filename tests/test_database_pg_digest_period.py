import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bot import database_pg


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


if __name__ == "__main__":
    unittest.main()
