"""Tests for guest label formatting."""

import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.texts import format_going_entry, format_guest_suffix  # noqa: E402


class GuestFormatTest(unittest.TestCase):
    def test_suffix_forms(self):
        self.assertEqual(format_guest_suffix(0), "")
        self.assertEqual(format_guest_suffix(1), " + 1 гость")
        self.assertEqual(format_guest_suffix(2), " + 2 гостя")
        self.assertEqual(format_guest_suffix(5), " + 5 гостей")
        self.assertEqual(format_guest_suffix(21), " + 21 гость")
        self.assertEqual(format_guest_suffix(12), " + 12 гостей")

    def test_going_entry(self):
        self.assertEqual(format_going_entry("@TeaFox240", 2), "@TeaFox240 + 2 гостя")
        self.assertEqual(format_going_entry("@TeaFox240", 0), "@TeaFox240")


if __name__ == "__main__":
    unittest.main()
