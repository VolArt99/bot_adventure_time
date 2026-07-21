import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import types

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DIGEST_DAY_OF_WEEK", "3")
os.environ.setdefault("DIGEST_HOUR", "14")

from bot.utils import scheduler  # noqa: E402


class SchedulerConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_digest_uses_config_values(self):
        fake_bot = object()
        fake_digest_module = types.SimpleNamespace(send_digest=AsyncMock())
        with (
            patch.dict(sys.modules, {"bot.handlers.digest": fake_digest_module}),
            patch("bot.utils.scheduler.DIGEST_DAY_OF_WEEK", 3),
            patch("bot.utils.scheduler.DIGEST_HOUR", 14),
            patch.object(scheduler.scheduler, "add_job") as add_job,
        ):
            await scheduler.schedule_digest(fake_bot, chat_id=1, thread_id=2)

        _, kwargs = add_job.call_args
        self.assertEqual(kwargs["day_of_week"], 2)
        self.assertEqual(kwargs["hour"], 14)

    async def test_reminder_is_sent_only_as_private_dm(self):
        bot = SimpleNamespace(
            send_message=AsyncMock(
                return_value=SimpleNamespace(message_id=999),
            ),
            delete_message=AsyncMock(),
        )
        send_private_dm = AsyncMock(return_value=501)

        with (
            patch("bot.utils.scheduler.get_event", new=AsyncMock(return_value={
                "id": 100,
                "status": "active",
                "title": "Событие",
                "date_time": "2026-06-01T10:00:00+00:00",
                "location": "Москва",
                "thread_id": 10,
                "message_id": 55,
            })),
            patch("bot.utils.scheduler.get_participants", new=AsyncMock(return_value=[123])),
            patch("bot.utils.notifications.send_private_dm", new=send_private_dm),
        ):
            await scheduler.send_reminder(100, 3600, bot)

        bot.send_message.assert_not_awaited()
        send_private_dm.assert_awaited_once()
        text = send_private_dm.await_args.args[2]
        self.assertIn("1 ч", text)
        self.assertIn("Открыть карточку", text)


if __name__ == "__main__":
    unittest.main()
