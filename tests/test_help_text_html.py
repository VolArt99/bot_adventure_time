import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")

from bot.handlers.common_feature.views import (
    build_approval_message,
    build_command_action_text,
    build_help_text,
    build_main_menu_text,
    build_menu_section_text,
    build_group_rules_text,
    build_onboarding_guard_text,
    build_onboarding_welcome_text,
    build_owner_request_text,
)
from bot.keyboards import event_actions, main_menu_keyboard, menu_section_keyboard, quick_event_templates_keyboard, start_menu_keyboard
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
        self.assertIn("✅ В путь", text)

    def test_main_menu_text_and_sections_are_styled(self):
        menu_text = build_main_menu_text(is_admin_or_owner=True)
        section_text = build_menu_section_text("events", is_admin_or_owner=False)

        self.assertIn("Adventure Time Control Center", menu_text)
        self.assertIn("Куда отправимся", menu_text)
        self.assertIn(CARD_DIVIDER, menu_text)
        self.assertIn("Что делает каждая кнопка", menu_text)
        self.assertIn("🟣🎉 <b>События</b>", menu_text)
        self.assertIn("🟢🧾 <b>Деньги</b>", menu_text)
        self.assertIn("🔵🔔 <b>Уведомления</b>", menu_text)
        self.assertIn("🟠🤝 <b>Комьюнити</b>", menu_text)
        self.assertIn("🟣🎉 <b>События</b>", section_text)
        self.assertIn("👉 <i>", section_text)


    def test_onboarding_and_owner_texts_are_view_builders(self):
        approval = build_approval_message(
            invite_link="https://t.me/+invite&x=<tag>",
            owner_contact_html='<a href="https://t.me/source_owner">@source_owner</a>',
        )
        owner_request = build_owner_request_text(
            user_id=42,
            full_name="<Alice> & Bob",
            username="bad<tag>",
        )

        self.assertIn("Дверь открыта", approval)
        self.assertIn("https://t.me/+invite&amp;x=&lt;tag&gt;", approval)
        self.assertIn("@source_owner", approval)
        self.assertIn("Шаг 1/3 · Старт", build_onboarding_welcome_text())
        self.assertIn("Шаг 2/3 · Правила", build_group_rules_text())
        self.assertIn("Шаг 3/3 · Вход в группу", approval)
        self.assertIn("Правила изучил(а)", build_onboarding_guard_text())
        self.assertIn("&lt;Alice&gt; &amp; Bob", owner_request)
        self.assertIn("@bad&lt;tag&gt;", owner_request)


    def test_menu_exposes_grouped_command_buttons(self):
        main_menu = main_menu_keyboard(is_admin_or_owner=True)
        labels = [button.text for row in main_menu.inline_keyboard for button in row]

        self.assertNotIn("🧭 Все команды", labels)
        self.assertIn("🎉 События", labels)
        self.assertIn("🧾 Деньги", labels)
        self.assertIn("🔔 Уведомления", labels)
        self.assertIn("🤝 Комьюнити", labels)

        event_menu = menu_section_keyboard("events", is_admin_or_owner=False)
        event_labels = [button.text for row in event_menu.inline_keyboard for button in row]

        self.assertIn("🎉 /create_event", event_labels)
        self.assertIn("🏠 Главное меню", event_labels)


    def test_event_card_keyboard_uses_compact_cta_layout(self):
        keyboard = event_actions(42, carpool_enabled=True)
        rows = [[button.text for button in row] for row in keyboard.inline_keyboard]

        self.assertEqual(rows[0], ["✅ В путь!", "⏳ В резерве"])
        self.assertEqual(rows[1], ["❌ В другой раз"])
        self.assertEqual(rows[2], ["🚗 Водитель", "👥 Попутка"])
        self.assertEqual(rows[-1], ["🗑 Удалить"])

        
    def test_menu_separates_action_and_help_callbacks(self):
        event_menu = menu_section_keyboard("events", is_admin_or_owner=False)
        event_callbacks = {button.text: button.callback_data for row in event_menu.inline_keyboard for button in row}
        
        self.assertEqual(event_callbacks["🎉 /create_event"], "menu_action_create_event")
        self.assertEqual(event_callbacks["🔗 /send_event_card"], "menu_cmd_send_event_card")

    def test_command_action_text_contains_examples(self):
        text = build_command_action_text("find_events")

        self.assertIn("/find_events", text)
        self.assertIn("&lt;текст&gt;", text)
        self.assertIn("<code>/find_events квиз</code>", text)        


class MenuKeyboardRegressionTests(unittest.TestCase):
    def test_main_menu_sections_do_not_duplicate_commands(self):
        section_names = {"events", "money", "notifications", "community", "help"}
        seen: dict[str, str] = {}

        for section in section_names:
            keyboard = menu_section_keyboard(section, is_admin_or_owner=False)
            for row in keyboard.inline_keyboard:
                for button in row:
                    if not button.text.startswith(("/", "🎉 /", "📅 /", "📣 /", "🔎 /", "🔗 /", "👤 /", "➕ /", "🚗 /", "👥 /", "🧾 /", "➖ /", "🔔 /", "✨ /", "🤝 /", "🚫 /", "📈 /", "🏆 /", "❓ /", "✅ /")):
                        continue
                    command = button.text.split()[-1]
                    self.assertNotIn(command, seen, f"{command} repeats in {section} and {seen.get(command)}")
                    seen[command] = section

    def test_quick_templates_replace_dinner_with_group_formats(self):
        keyboard = quick_event_templates_keyboard()
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertNotIn("🍽 Ужин", labels)
        self.assertIn("💪 Спорт", labels)
        self.assertIn("🗣 Языковой клуб", labels)
        self.assertIn("🖥 Кооп на ПК", labels)

    def test_start_menu_keyboard_opens_menu(self):
        keyboard = start_menu_keyboard()
        button = keyboard.inline_keyboard[0][0]

        self.assertEqual(button.text, "🏠 Открыть /menu")
        self.assertEqual(button.callback_data, "menu_home")

        
if __name__ == "__main__":
    unittest.main()
