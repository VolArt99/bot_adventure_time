import os
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.utils.callback_rate_limit import is_callback_rate_limited  # noqa: E402
from bot.utils.notifications import is_quiet_hours, next_quiet_hours_end  # noqa: E402
from bot.texts import get_group_rules_text  # noqa: E402


class QuietHoursTests(unittest.TestCase):
    def test_overnight_quiet_hours(self):
        with (
            patch("bot.utils.notifications.QUIET_HOURS_START", 23),
            patch("bot.utils.notifications.QUIET_HOURS_END", 8),
        ):
            night = datetime(2026, 7, 14, 23, 30, tzinfo=__import__("pytz").timezone("Europe/Moscow"))
            morning = datetime(2026, 7, 15, 7, 0, tzinfo=__import__("pytz").timezone("Europe/Moscow"))
            day = datetime(2026, 7, 15, 12, 0, tzinfo=__import__("pytz").timezone("Europe/Moscow"))
            self.assertTrue(is_quiet_hours(night))
            self.assertTrue(is_quiet_hours(morning))
            self.assertFalse(is_quiet_hours(day))

    def test_next_quiet_hours_end_after_start(self):
        with (
            patch("bot.utils.notifications.QUIET_HOURS_START", 23),
            patch("bot.utils.notifications.QUIET_HOURS_END", 8),
        ):
            import pytz

            tz = pytz.timezone("Europe/Moscow")
            night = tz.localize(datetime(2026, 7, 14, 23, 30))
            end = next_quiet_hours_end(night)
            self.assertEqual(end.hour, 8)
            self.assertEqual(end.day, 15)


class CallbackRateLimitTests(unittest.TestCase):
    def test_second_hit_is_limited(self):
        scope = "test_scope"
        self.assertFalse(is_callback_rate_limited(scope, 1, 10, "join", now=100.0))
        self.assertTrue(is_callback_rate_limited(scope, 1, 10, "join", now=100.5))
        self.assertFalse(is_callback_rate_limited(scope, 1, 10, "join", now=102.0))


class GroupRulesContactTests(unittest.TestCase):
    def test_rules_use_owner_contact_not_hardcoded_fallback_when_set(self):
        with (
            patch("bot.config.OWNER_CONTACT", "@demo_admin"),
            patch("bot.config.OWNER_ID", 42),
        ):
            text = get_group_rules_text()
        self.assertIn("@demo_admin", text)
        self.assertNotIn("@Vol_Artem", text)
