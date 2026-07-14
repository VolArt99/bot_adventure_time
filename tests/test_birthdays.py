import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.db.birthdays import (  # noqa: E402
    format_birthday_display,
    parse_birthday_input,
)
from bot.db.topics import resolve_thread_id_by_name_fragment  # noqa: E402


class BirthdayParseTests(unittest.TestCase):
    def test_parse_dd_mm(self):
        self.assertEqual(parse_birthday_input("15.07"), "07-15")
        self.assertEqual(parse_birthday_input("5.3"), "03-05")

    def test_parse_with_year_ignored(self):
        self.assertEqual(parse_birthday_input("15.07.1990"), "07-15")
        self.assertEqual(parse_birthday_input("15/07/90"), "07-15")

    def test_parse_invalid(self):
        self.assertIsNone(parse_birthday_input("32.01"))
        self.assertIsNone(parse_birthday_input("15.13"))
        self.assertIsNone(parse_birthday_input("abc"))

    def test_format_display(self):
        self.assertEqual(format_birthday_display("07-15"), "15.07")


class BirthdayTopicResolveTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_by_name_fragment_from_db(self):
        with patch(
            "bot.db.topics.get_all_topics",
            new=AsyncMock(
                return_value=[
                    {"message_thread_id": 999, "name": "💌 Общение и не только"},
                ]
            ),
        ):
            thread_id = await resolve_thread_id_by_name_fragment("Общение и не только")
        self.assertEqual(thread_id, 999)


class BirthdayGreetingTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_daily_posts_to_community_topic(self):
        from datetime import datetime
        from unittest.mock import MagicMock

        from bot.utils.birthdays import send_daily_birthday_greetings

        bot = AsyncMock()
        bot.send_message = AsyncMock()
        mock_now = MagicMock()
        mock_now.date.return_value = date(2026, 7, 15)

        with (
            patch("bot.utils.birthdays.GROUP_ID", -100123),
            patch("bot.utils.birthdays.resolve_birthday_thread_id", new=AsyncMock(return_value=1)),
            patch(
                "bot.utils.birthdays.get_approved_members_with_birthday_on",
                new=AsyncMock(return_value=[{"user_id": 42, "username": "ivan"}]),
            ) as get_today,
            patch("bot.utils.birthdays.was_birthday_greeted", new=AsyncMock(return_value=False)),
            patch("bot.utils.birthdays.record_birthday_greeting", new=AsyncMock()),
            patch("bot.utils.birthdays.get_user_mention", new=AsyncMock(return_value="@ivan")),
            patch("bot.utils.birthdays.datetime") as dt_mock,
        ):
            dt_mock.now.return_value = mock_now
            count = await send_daily_birthday_greetings(bot)

        self.assertEqual(count, 1)
        get_today.assert_awaited_once_with("07-15")
        bot.send_message.assert_awaited_once()
        _, kwargs = bot.send_message.await_args
        self.assertEqual(kwargs["message_thread_id"], 1)
        self.assertIn("@ivan", kwargs["text"])
