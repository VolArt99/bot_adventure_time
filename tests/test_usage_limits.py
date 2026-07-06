import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytz

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("TIMEZONE", "Europe/Moscow")

from bot.db.usage import usage_date_key  # noqa: E402
from bot.middleware.command_access import CommandAccessMiddleware  # noqa: E402


class UsageDateKeyTests(unittest.TestCase):
    def test_usage_date_key_uses_bot_timezone(self):
        tz = pytz.timezone("Europe/Moscow")
        moment = tz.localize(datetime(2026, 7, 6, 1, 30))
        self.assertEqual(usage_date_key(moment), "2026-07-06")

    def test_usage_date_key_converts_from_utc(self):
        tz = pytz.timezone("Europe/Moscow")
        # 2026-07-05 22:00 UTC = 2026-07-06 01:00 MSK
        moment = datetime(2026, 7, 5, 22, 0, tzinfo=pytz.UTC)
        self.assertEqual(usage_date_key(moment), "2026-07-06")


class _FakeCallback:
    def __init__(self, user_id: int, data: str):
        self.from_user = type("U", (), {"id": user_id})()
        self.data = data
        self.answer = AsyncMock()
        self.message = type("M", (), {"chat": type("C", (), {"type": "private"})()})()


class _FakeState:
    def __init__(self, current_state: str | None):
        self._current_state = current_state

    async def get_state(self):
        return self._current_state


class WizardLimitExemptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_wizard_callback_skips_daily_limit_increment(self):
        middleware = CommandAccessMiddleware()
        callback = _FakeCallback(user_id=555, data="event_back")
        handler = AsyncMock()
        state = _FakeState("CreateEvent:category")

        with (
            patch("bot.middleware.command_access.is_member_approved", new=AsyncMock(return_value=True)),
            patch(
                "bot.middleware.command_access.get_user_daily_command_count",
                new=AsyncMock(return_value=999),
            ) as get_count,
            patch(
                "bot.middleware.command_access.increment_user_daily_command_count",
                new=AsyncMock(),
            ) as increment_count,
            patch("bot.middleware.command_access.record_command_usage", new=AsyncMock()),
        ):
            await middleware(handler, callback, {"state": state})

        handler.assert_awaited_once()
        get_count.assert_not_awaited()
        increment_count.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
