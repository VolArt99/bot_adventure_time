import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.utils.telegram_errors import (
    is_benign_telegram_error,
    is_harmless_callback_answer_error,
    safe_callback_answer,
)


class TelegramErrorsTests(unittest.TestCase):
    def test_stale_callback_is_benign(self):
        exc = TelegramBadRequest(
            method="answerCallbackQuery",
            message="Bad Request: query is too old and response timeout expired or query ID is invalid",
        )
        self.assertTrue(is_harmless_callback_answer_error(exc))
        self.assertTrue(is_benign_telegram_error(exc))

    def test_forbidden_is_benign(self):
        exc = TelegramForbiddenError(
            method="sendMessage",
            message="Forbidden: bot was blocked by the user",
        )
        self.assertTrue(is_benign_telegram_error(exc))

    def test_unexpected_bad_request_is_not_benign(self):
        exc = TelegramBadRequest(method="sendMessage", message="Bad Request: chat not found")
        self.assertFalse(is_benign_telegram_error(exc))


class SafeCallbackAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_swallows_stale_callback_error(self):
        callback = SimpleNamespace(
            id="cb-1",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(
                side_effect=TelegramBadRequest(
                    method="answerCallbackQuery",
                    message="Bad Request: query is too old and response timeout expired or query ID is invalid",
                )
            ),
        )

        answered = await safe_callback_answer(callback, "ok")

        self.assertFalse(answered)
        callback.answer.assert_awaited_once()

    async def test_returns_true_on_success(self):
        callback = SimpleNamespace(
            id="cb-2",
            from_user=SimpleNamespace(id=2),
            answer=AsyncMock(),
        )

        answered = await safe_callback_answer(callback, "done", show_alert=True)

        self.assertTrue(answered)
        callback.answer.assert_awaited_once_with(text="done", show_alert=True)


if __name__ == "__main__":
    unittest.main()
