"""Tests for duration text parsing."""

import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.utils.duration import apply_duration_unit, parse_duration_text  # noqa: E402


class DurationParseTest(unittest.TestCase):
    def test_hours_and_minutes(self):
        result = parse_duration_text("1 ч 30 мин")
        self.assertEqual(result.minutes, 90)
        self.assertFalse(result.needs_unit)

    def test_compact_russian(self):
        self.assertEqual(parse_duration_text("1ч 30м").minutes, 90)

    def test_hours_only(self):
        self.assertEqual(parse_duration_text("2.5 ч").minutes, 150)
        self.assertEqual(parse_duration_text("2,5 часа").minutes, 150)

    def test_minutes_only(self):
        self.assertEqual(parse_duration_text("90 мин").minutes, 90)
        self.assertEqual(parse_duration_text("300 минут").minutes, 300)

    def test_bare_number_needs_unit(self):
        result = parse_duration_text("300")
        self.assertTrue(result.needs_unit)
        self.assertEqual(result.raw_value, 300.0)
        self.assertIsNone(result.minutes)

    def test_skip(self):
        self.assertIsNone(parse_duration_text("пропустить").minutes)
        self.assertIsNone(parse_duration_text("-").minutes)

    def test_apply_unit(self):
        self.assertEqual(apply_duration_unit(300, "minutes"), 300)
        self.assertEqual(apply_duration_unit(2.5, "hours"), 150)

    def test_bad_format(self):
        self.assertEqual(parse_duration_text("долго").error, "bad_format")


if __name__ == "__main__":
    unittest.main()
