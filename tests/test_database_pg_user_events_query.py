import unittest
from unittest.mock import AsyncMock, patch

from bot import database_pg


class DatabasePgUserEventsQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_user_events_executes_query(self):
        fake_pool = AsyncMock()
        fake_pool.retry_operation = AsyncMock()

        async def fake_run_query(query, parameters=None):
            self.assertIn("creator_id = $user_id", query)
            self.assertEqual(parameters, {"user_id": 42})
            return [database_pg._CompatResultSet([])]

        with patch("bot.database_pg._run_query", side_effect=fake_run_query):
            await database_pg.get_user_events(user_id=42, status="organizer")


if __name__ == "__main__":
    unittest.main()
