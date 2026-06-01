import os
import unittest
from datetime import datetime

os.environ.setdefault("BOT_TOKEN", "test-token")

from bot.texts import event_status_badges, format_duration, format_event_period, category_to_hashtags, category_to_branded_hashtags  # noqa: E402
from bot.utils.event_links import (  # noqa: E402
    build_google_calendar_link,
    build_maps_link,
    build_yandex_maps_link,
    build_yandex_navigator_link,
)
from bot.utils.pairing import build_random_pairs  # noqa: E402
from bot.handlers.event_scenarios.shared import CreateEvent, event_step_prompt  # noqa: E402
from bot.handlers.split_bill_feature.handlers import SplitBillCreate, split_bill_step_prompt  # noqa: E402
from bot.handlers.split_bill_feature.services import build_payment_progress_bar  # noqa: E402
from bot.texts import format_digest_text  # noqa: E402

class TextFormattersTest(unittest.TestCase):
    def test_format_duration_hours_and_minutes(self):
        self.assertEqual(format_duration(90), "1 ч 30 мин")

    def test_format_duration_empty(self):
        self.assertEqual(format_duration(None), "не указана")

    def test_category_to_hashtags(self):
        self.assertEqual(category_to_hashtags("спорт, поездки"), "#спорт #поездки")

    def test_category_to_branded_hashtags(self):
        self.assertEqual(
            category_to_branded_hashtags("настолки, книжный клуб"),
            "🎲 Настолки #настолки 📚 Книги #книжный_клуб",
        )

    def test_event_status_badges(self):
        event = {
            "date_time": "2026-06-01T12:00:00+03:00",
            "participant_limit": 2,
        }
        now = datetime.fromisoformat("2026-06-01T09:00:00+03:00")

        self.assertEqual(event_status_badges(event, 1, 0, now=now), "🔥 скоро · ✅ набор открыт")
        self.assertEqual(event_status_badges(event, 2, 0, now=now), "🔥 скоро · 🚫 мест нет")
        self.assertEqual(event_status_badges(event, 2, 1, now=now), "🔥 скоро · ⏳ резерв")

    def test_format_event_period(self):
        start_dt = datetime.fromisoformat("2026-06-01T10:00:00+03:00")
        text = format_event_period(start_dt, "2026-06-30T23:59:00+03:00")
        self.assertEqual(text, "📆 Период: 01.06.2026 10:00 — 30.06.2026 23:59")

    def test_format_event_period_empty_for_regular_event(self):
        start_dt = datetime.fromisoformat("2026-06-01T10:00:00+03:00")
        self.assertIsNone(format_event_period(start_dt, None))
        self.assertIsNone(format_event_period(start_dt, ""))

class FeatureHelpersTest(unittest.TestCase):
    def test_maps_and_calendar_links(self):
        event = {
            "id": 1,
            "title": "Вело",
            "description": "Тренировка",
            "location": "Санкт-Петербург, Невский 1",
            "date_time": "2026-06-01T10:00:00",
            "duration_minutes": 90,
            "period_end": "2026-06-05T10:00:00",
        }

        calendar_link = build_google_calendar_link(event)
        
        self.assertIn("google.com/maps", build_maps_link(event["location"]))
        yandex_navigator_link = build_yandex_navigator_link(event["location"])
        yandex_maps_link = build_yandex_maps_link(event["location"])
        self.assertTrue(yandex_navigator_link.startswith("https://"))
        self.assertIn("https://yandex.ru/navi/?text=", yandex_navigator_link)
        self.assertIn("%D0%A1%D0%B0%D0%BD%D0%BA%D1%82", yandex_navigator_link)
        self.assertTrue(yandex_maps_link.startswith("https://"))
        self.assertIn("https://yandex.ru/maps/?mode=search&text=", yandex_maps_link)
        self.assertNotIn("/navi/", yandex_maps_link)
        self.assertIn("%D0%A1%D0%B0%D0%BD%D0%BA%D1%82", yandex_maps_link)
        self.assertIn("calendar.google.com", calendar_link)
        self.assertIn("dates=20260601T100000%2F20260605T100000", calendar_link)

    def test_regular_event_calendar_link_uses_duration_without_period(self):
        event = {
            "title": "Вело",
            "date_time": "2026-06-01T10:00:00",
            "duration_minutes": 90,
            "period_end": "",
        }

        calendar_link = build_google_calendar_link(event)

        self.assertIn("dates=20260601T100000%2F20260601T113000", calendar_link)

    def test_build_random_pairs(self):
        pairs, leftovers = build_random_pairs([1, 2, 3])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(leftovers), 1)

    def test_wizard_progress_prompts(self):
        self.assertIn("Шаг 7/12 · 📍 Место", event_step_prompt(CreateEvent.location.state, "Введите место"))
        self.assertIn("Шаг 4/7 · 🗂 Публикация", split_bill_step_prompt(SplitBillCreate.target_topic.state, "Выберите тему"))

    def test_split_bill_payment_progress_bar(self):
        self.assertEqual(build_payment_progress_bar(4, 6), "████░░ 4/6 оплатили")
        self.assertEqual(build_payment_progress_bar(0, 0), "░░░░░░ 0/0 оплатили")

    def test_digest_uses_event_counts_for_status_badges(self):
        text = format_digest_text(
            [
                {
                    "id": 1,
                    "title": "Квиз",
                    "date_time": "2026-06-01T12:00:00+03:00",
                    "creator_id": 10,
                    "participant_limit": 2,
                    "going_count": 2,
                    "waitlist_count": 1,
                }
            ],
            {10: "owner"},
        )

        self.assertIn("⏳ резерв", text)        

if __name__ == "__main__":
    unittest.main()
