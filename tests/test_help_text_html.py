import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")

from bot.handlers.common_feature.views import build_command_action_text, build_help_text, build_main_menu_text, build_menu_section_text
from bot.keyboards import main_menu_keyboard, menu_section_keyboard
from bot.utils.design import CARD_DIVIDER


class HelpTextHtmlTests(unittest.TestCase):
    def test_help_text_does_not_contain_unescaped_placeholders(self):
        text = build_help_text(is_admin_or_owner=True)

        self.assertNotIn("<текст>", text)
        self.assertNotIn("<id>", text)
        self.assertIn("&lt;текст&gt;", text)
        self.assertIn("&lt;id&gt;", text)

    def test_help_text_mentions_visual_menu(self):
        text = build_help_text(is_admin_or_owner=False)

        self.assertIn("/menu", text)
        self.assertIn("Описание кнопок", text)
        self.assertIn("✅ Пойду", text)

    def test_main_menu_text_and_sections_are_styled(self):
        menu_text = build_main_menu_text(is_admin_or_owner=True)
        section_text = build_menu_section_text("create_event", is_admin_or_owner=False)

        self.assertIn("Adventure Time Control Center", menu_text)
        self.assertIn(CARD_DIVIDER, menu_text)
        self.assertIn("Что делает каждая кнопка", menu_text)
        self.assertIn("<b>🎉 Создать</b>", menu_text)
        self.assertIn("🎉 <b>Создание мероприятия</b>", section_text)
        self.assertIn("Кнопки раздела", section_text)
        self.assertIn("👉 <i>", section_text)

    def test_menu_exposes_grouped_command_buttons(self):
        main_menu = main_menu_keyboard(is_admin_or_owner=True)
        labels = [button.text for row in main_menu.inline_keyboard for button in row]

        self.assertIn("🧭 Все команды", labels)

        event_menu = menu_section_keyboard("create_event", is_admin_or_owner=False)
        event_labels = [button.text for row in event_menu.inline_keyboard for button in row]

        self.assertIn("🎉 /create_event", event_labels)
        self.assertIn("🏠 Главное меню", event_labels)

    def test_menu_separates_action_and_help_callbacks(self):
        event_menu = menu_section_keyboard("create_event", is_admin_or_owner=False)
        event_callbacks = {button.text: button.callback_data for row in event_menu.inline_keyboard for button in row}
        my_events_menu = menu_section_keyboard("my_events", is_admin_or_owner=False)
        my_events_callbacks = {button.text: button.callback_data for row in my_events_menu.inline_keyboard for button in row}

        self.assertEqual(event_callbacks["🎉 /create_event"], "menu_action_create_event")
        self.assertEqual(my_events_callbacks["🔗 /send_event_card"], "menu_cmd_send_event_card")

    def test_command_action_text_contains_examples(self):
        text = build_command_action_text("find_events")

        self.assertIn("/find_events", text)
        self.assertIn("&lt;текст&gt;", text)
        self.assertIn("<code>/find_events квиз</code>", text)        

if __name__ == "__main__":
    unittest.main()
