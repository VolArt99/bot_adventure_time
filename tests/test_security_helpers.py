import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")

from bot.utils.callbacks import parse_callback_split_int, parse_callback_suffix_int
from bot.utils.command_policy import can_view_command_hint


class CallbackParsingTests(unittest.TestCase):
    def test_parse_callback_suffix_int(self):
        self.assertEqual(parse_callback_suffix_int("seek_ride_42", prefix="seek_ride_"), 42)
        self.assertIsNone(parse_callback_suffix_int("seek_ride_x", prefix="seek_ride_"))
        self.assertIsNone(parse_callback_suffix_int(None, prefix="seek_ride_"))

    def test_parse_callback_split_int(self):
        self.assertEqual(parse_callback_split_int("join_100", index=1, min_parts=2), 100)
        self.assertIsNone(parse_callback_split_int("join_", index=1, min_parts=2))
        self.assertEqual(parse_callback_split_int("choose_driver_10_20", index=2, min_parts=4), 10)


class CommandPolicyTests(unittest.TestCase):
    def test_member_cannot_view_admin_command_hint(self):
        self.assertFalse(
            can_view_command_hint("debug_info", 555, is_approved_member=True),
        )

    def test_admin_can_view_admin_command_hint(self):
        import bot.utils.command_policy as policy

        with unittest.mock.patch.object(policy, "is_admin_or_owner", return_value=True):
            self.assertTrue(
                can_view_command_hint("debug_info", 1, is_approved_member=False),
            )


if __name__ == "__main__":
    unittest.main()
