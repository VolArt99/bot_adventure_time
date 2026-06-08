import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE, CALLBACK_KEEP_PUBLIC_MESSAGE
from bot.utils.callbacks import finalize_callback


class FinalizeCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_flag_deletes_bot_message(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(is_bot=True),
            delete=AsyncMock(),
        )
        callback = SimpleNamespace(answer=AsyncMock(), message=message)

        await finalize_callback(callback, "ok", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)

        callback.answer.assert_awaited_once_with(text="ok", show_alert=False)
        message.delete.assert_awaited_once()

    async def test_keep_policy_does_not_delete_public_message(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(is_bot=True),
            chat=SimpleNamespace(type="supergroup"),
            delete=AsyncMock(),
        )
        callback = SimpleNamespace(answer=AsyncMock(), message=message)

        await finalize_callback(callback, delete_message=CALLBACK_KEEP_PUBLIC_MESSAGE)

        callback.answer.assert_awaited_once_with(text=None, show_alert=False)
        message.delete.assert_not_awaited()


    async def test_keep_policy_keeps_private_bot_message(self):
        message = SimpleNamespace(
            from_user=SimpleNamespace(is_bot=True),
            chat=SimpleNamespace(type="private"),
            delete=AsyncMock(),
        )
        callback = SimpleNamespace(answer=AsyncMock(), message=message)

        await finalize_callback(callback, delete_message=CALLBACK_KEEP_PUBLIC_MESSAGE)

        callback.answer.assert_awaited_once_with(text=None, show_alert=False)
        message.delete.assert_not_awaited()

    async def test_delete_flag_deletes_callback_message_without_sender_by_id(self):
        bot = SimpleNamespace(delete_message=AsyncMock())
        message = SimpleNamespace(
            bot=bot,
            chat=SimpleNamespace(id=42, type="private"),
            message_id=99,
        )
        callback = SimpleNamespace(answer=AsyncMock(), message=message)

        await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)

        bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=99)

    async def test_no_message_only_answers(self):
        callback = SimpleNamespace(answer=AsyncMock(), message=None)

        await finalize_callback(callback, "done", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)

        callback.answer.assert_awaited_once_with(text="done", show_alert=False)

    async def test_show_alert_is_passed_to_answer(self):
        callback = SimpleNamespace(answer=AsyncMock(), message=None)

        await finalize_callback(callback, "alert", show_alert=True)

        callback.answer.assert_awaited_once_with(text="alert", show_alert=True)

    async def test_skip_answer_does_not_call_answer(self):
        callback = SimpleNamespace(answer=AsyncMock(), message=None)

        await finalize_callback(callback, "ignored", skip_answer=True)

        callback.answer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
