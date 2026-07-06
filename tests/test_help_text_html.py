import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")

from bot.commands import COMMAND_SPECS
from bot.handlers.common_feature.views import (
    build_approval_message,
    build_command_action_text,
    build_group_rules_full_text,
    build_group_rules_text,
    build_help_text,
    build_main_menu_text,
    build_menu_section_text,
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
        self.assertIn("<b>События</b>", menu_text)
        self.assertIn("🎉", section_text)
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
        self.assertNotIn("Политика, ЛГБТ", build_group_rules_text())
        self.assertIn("Политика, ЛГБТ", build_group_rules_full_text())
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
        self.assertIn("🔴 Админ", labels)

        event_menu = menu_section_keyboard("events", is_admin_or_owner=False)
        event_labels = [button.text for row in event_menu.inline_keyboard for button in row]

        self.assertIn("👀 Смотреть", event_labels)
        self.assertIn("➕ Создать", event_labels)
        self.assertIn("🛠 Управление", event_labels)

    def test_event_card_keyboard_uses_compact_cta_layout(self):
        keyboard = event_actions(42, carpool_enabled=True)
        rows = [[button.text for button in row] for row in keyboard.inline_keyboard]

        self.assertEqual(rows[0], ["✅ В путь!", "⏳ В резерве"])
        self.assertEqual(rows[1], ["❌ В другой раз"])
        self.assertEqual(rows[2], ["🚗 Водитель", "👥 Попутка"])
        self.assertNotIn(["🗑 Удалить"], rows)

    def test_event_card_keyboard_personalized_for_going(self):
        keyboard = event_actions(42, participation_status="going")
        rows = [[button.text for button in row] for row in keyboard.inline_keyboard]
        self.assertEqual(rows[0], ["❌ Снять запись"])

    def test_menu_separates_action_and_help_callbacks(self):
        event_menu = menu_section_keyboard("events_create", is_admin_or_owner=False)
        event_callbacks = {button.text: button.callback_data for row in event_menu.inline_keyboard for button in row}

        self.assertEqual(event_callbacks["➕ Создать встречу"], "menu_action_create_event")
        manage_menu = menu_section_keyboard("events_manage", is_admin_or_owner=False)
        manage_callbacks = {button.text: button.callback_data for row in manage_menu.inline_keyboard for button in row}
        self.assertEqual(manage_callbacks["🔗 Ссылка на карточку"], "menu_cmd_send_event_card")
        self.assertEqual(manage_callbacks["✏️ Редактировать"], "menu_cmd_edit_event")

    def test_command_action_text_contains_examples(self):
        text = build_command_action_text("find_events")

        self.assertIn("/find_events", text)
        self.assertIn("&lt;текст&gt;", text)
        self.assertIn("<code>/find_events квиз</code>", text)

    def test_help_lists_all_member_commands_from_registry(self):
        text = build_help_text(is_admin_or_owner=False)
        for spec in COMMAND_SPECS:
            if spec.group == "admin":
                continue
            self.assertIn(f"/{spec.command}", text, msg=f"missing /{spec.command} in member help")

    def test_help_lists_all_admin_commands_for_admin(self):
        text = build_help_text(is_admin_or_owner=True)
        for spec in COMMAND_SPECS:
            if spec.group != "admin":
                continue
            self.assertIn(f"/{spec.command}", text, msg=f"missing /{spec.command} in admin help")

    def _menu_command_callbacks(self, *, is_admin_or_owner: bool = False) -> set[str]:
        names: set[str] = set()
        sections = (
            "events_browse",
            "events_create",
            "events_manage",
            "money",
            "notifications",
            "community",
            "help",
        )
        if is_admin_or_owner:
            sections = (*sections, "admin")
        for section in sections:
            keyboard = menu_section_keyboard(section, is_admin_or_owner=is_admin_or_owner)
            for row in keyboard.inline_keyboard:
                for button in row:
                    data = button.callback_data or ""
                    if data.startswith("menu_cmd_"):
                        names.add(data.removeprefix("menu_cmd_"))
                    elif data.startswith("menu_action_"):
                        names.add(data.removeprefix("menu_action_"))
        return names

    def test_menu_lists_all_member_commands_from_registry(self):
        menu_commands = self._menu_command_callbacks()
        action_map = {
            "create_event": "create_event",
            "my_events": "my_events",
            "digest": "digest",
            "subscriptions": "subscriptions",
            "my_digest": "my_digest",
            "random_optin": "random_optin",
            "random_optout": "random_optout",
            "my_stats": "my_stats",
            "top": "top",
            "split_bill": "split_bill",
            "donate": "donate",
        }
        excluded = {"start", "menu"}
        for spec in COMMAND_SPECS:
            if spec.group == "admin" or spec.command in excluded:
                continue
            in_menu = spec.command in menu_commands or spec.command in action_map.values()
            self.assertTrue(
                in_menu,
                msg=f"/{spec.command} missing from /menu sections",
            )

    def test_menu_lists_all_admin_commands_for_admin_section(self):
        menu_commands = self._menu_command_callbacks(is_admin_or_owner=True)
        for spec in COMMAND_SPECS:
            if spec.group != "admin":
                continue
            in_menu = spec.command in menu_commands or spec.command in {
                "roles",
                "usage_stats",
                "admin_report",
                "send_events_list",
                "random_pairs",
                "reset_user_limit",
            }
            self.assertTrue(in_menu, msg=f"/{spec.command} missing from admin menu section")


class MenuKeyboardRegressionTests(unittest.TestCase):
    def test_main_menu_sections_do_not_duplicate_commands(self):
        section_names = {"events_browse", "events_create", "events_manage", "money", "notifications", "community", "help"}
        seen: dict[str, str] = {}

        for section in section_names:
            keyboard = menu_section_keyboard(section, is_admin_or_owner=False)
            for row in keyboard.inline_keyboard:
                for button in row:
                    data = button.callback_data or ""
                    if not data.startswith(("menu_cmd_", "menu_action_")):
                        continue
                    command = data.removeprefix("menu_cmd_").removeprefix("menu_action_")
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

        self.assertEqual(button.text, "🏠 Открыть меню")
        self.assertEqual(button.callback_data, "menu_home")


if __name__ == "__main__":
    unittest.main()
