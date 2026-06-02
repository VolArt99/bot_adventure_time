import os
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("OWNER_ID", "12345")
from bot.middleware.command_access import CommandAccessMiddleware  # noqa: E402
from bot.utils.helpers import build_owner_contact_html  # noqa: E402

common = importlib.import_module("bot.handlers.common_feature.handlers")
participation = importlib.import_module("bot.handlers.participation")

class _FakeMessage:
    def __init__(self, user_id: int, text: str, chat_type: str = "private"):
        self.text = text
        self.chat = SimpleNamespace(type=chat_type)
        self.from_user = SimpleNamespace(id=user_id)
        self.answer = AsyncMock()


class _FakeCallback:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, username="u", first_name="A", last_name="B")
        self.data = data
        self.answer = AsyncMock()
        self.message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
        self.bot = SimpleNamespace(
            create_chat_invite_link=AsyncMock(return_value=SimpleNamespace(invite_link="https://t.me/+invite")),
            send_message=AsyncMock(),
        )


class _FakeState:
    def __init__(self, current_state: str | None):
        self._current_state = current_state
        self.clear = AsyncMock()

    async def get_state(self):
        return self._current_state


class CommandAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_outsider_help_command_is_denied(self):
        m = CommandAccessMiddleware()
        event = _FakeMessage(user_id=777, text="/help")
        handler = AsyncMock()

        with (
            patch("bot.middleware.command_access.Message", _FakeMessage),
            patch("bot.middleware.command_access.is_member_approved", new=AsyncMock(return_value=False)),
        ):
            await m(handler, event, {})

        handler.assert_not_awaited()
        event.answer.assert_awaited()


    async def test_new_command_clears_active_split_bill_scenario(self):
        m = CommandAccessMiddleware()
        event = _FakeMessage(user_id=777, text="/help")
        handler = AsyncMock()
        state = _FakeState("SplitBillCreate:amount")

        with (
            patch("bot.middleware.command_access.Message", _FakeMessage),
            patch("bot.middleware.command_access.is_member_approved", new=AsyncMock(return_value=False)),
        ):
            await m(handler, event, {"state": state})

        state.clear.assert_awaited_once()
        event.answer.assert_awaited()


class CommonCommandFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_command_has_no_menu_markup(self):
        message = _FakeMessage(user_id=11, text="/help")

        await common.cmd_help(message)

        _, kwargs = message.answer.await_args
        self.assertNotIn("reply_markup", kwargs)


    async def test_menu_command_has_main_menu_markup(self):
        message = _FakeMessage(user_id=11, text="/menu")

        await common.cmd_menu(message)

        args, kwargs = message.answer.await_args
        self.assertIn("Adventure Time Control Center", args[0])
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].callback_data, "menu_events")

        
    async def test_start_for_existing_member_points_to_menu(self):
        message = _FakeMessage(user_id=11, text="/start")
        message.from_user = SimpleNamespace(id=11, username="u", first_name="A", last_name="B")

        with (
            patch("bot.handlers.common_feature.handlers.get_or_create_user", new=AsyncMock()),
            patch("bot.handlers.common_feature.handlers.is_user_in_group", new=AsyncMock(return_value=True)),
            patch("bot.handlers.common_feature.handlers.upsert_approved_member", new=AsyncMock()),
        ):
            await common.cmd_start(message)

        args, kwargs = message.answer.await_args
        self.assertIn("/menu", args[0])
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].callback_data, "menu_home")

        
class OnboardingOwnerChecksTests(unittest.IsolatedAsyncioTestCase):
    async def test_approve_requires_owner_id(self):
        callback = _FakeCallback(user_id=999999, data="approve_user_42")

        await common.owner_approve_user(callback)

        callback.answer.assert_awaited()
        callback.bot.create_chat_invite_link.assert_not_awaited()


    def test_owner_contact_uses_clickable_owner_label_for_username(self):
        with patch.object(common, "OWNER_CONTACT", "@source_owner"):
            self.assertEqual(
                common._owner_contact_html(),
                '<a href="https://t.me/source_owner">владельцу</a>',
            )

    def test_owner_contact_uses_clickable_owner_label_for_link(self):
        with patch.object(common, "OWNER_CONTACT", "https://t.me/source_owner"):
            self.assertEqual(
                common._owner_contact_html(),
                '<a href="https://t.me/source_owner">владельцу</a>',
            )


    def test_owner_contact_strips_control_chars_and_escapes_text(self):
        self.assertEqual(
            build_owner_contact_html("bad\x00<contact>", 0),
            "bad&lt;contact&gt;",
        )


    def test_owner_contact_does_not_link_insecure_http_url(self):
        self.assertEqual(
            build_owner_contact_html("http://t.me/source_owner", 0),
            "http://t.me/source_owner",
        )

    async def test_approve_message_links_owner_contact(self):
        owner_callback = _FakeCallback(user_id=common.OWNER_ID, data="approve_user_42")

        with (
            patch.object(common, "OWNER_CONTACT", "@source_owner"),
            patch(
                "bot.handlers.common_feature.handlers.approve_pending_user",
                new=AsyncMock(return_value={"user_id": 42}),
            ),
        ):
            await common.owner_approve_user(owner_callback)

        owner_callback.bot.send_message.assert_awaited_once()
        args, kwargs = owner_callback.bot.send_message.await_args
        self.assertEqual(args[0], 42)
        self.assertIn('<a href="https://t.me/source_owner">владельцу</a>', args[1])
        self.assertEqual(kwargs["parse_mode"], "HTML")

        
    async def test_reject_flow_for_owner(self):
        owner_callback = _FakeCallback(user_id=common.OWNER_ID, data="reject_user_42")

        with patch("bot.handlers.common_feature.handlers.delete_pending_user", new=AsyncMock()) as delete_pending_user:
            await common.owner_reject_user(owner_callback)

        delete_pending_user.assert_awaited_once_with(42)
        owner_callback.bot.send_message.assert_awaited()
        owner_callback.message.edit_text.assert_awaited()


class ParticipationTransitionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_waitlist_denied_if_already_in_main_list(self):
        callback = _FakeCallback(user_id=11, data="waitlist_100")

        with (
            patch("bot.filters.approved_member.is_member_approved", new=AsyncMock(return_value=True)),
            patch("bot.handlers.participation.get_event", new=AsyncMock(return_value={"id": 100, "status": "active"})),
            patch("bot.handlers.participation.get_main_participants", new=AsyncMock(return_value=[11])),
        ):
            await participation.waitlist_event(callback)

        callback.answer.assert_awaited()


if __name__ == "__main__":
    unittest.main()
