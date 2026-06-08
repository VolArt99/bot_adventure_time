"""Классификация ожидаемых ошибок Telegram API и безопасные обёртки."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)

_HARMLESS_CALLBACK_ANSWER_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
    "query is already answered",
)


def is_harmless_callback_answer_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _HARMLESS_CALLBACK_ANSWER_MARKERS)


def is_benign_telegram_error(exc: Exception) -> bool:
    """Ошибки, которые не требуют алерта владельцу и уведомления пользователя."""
    if isinstance(exc, TelegramForbiddenError):
        return True
    if isinstance(exc, TelegramBadRequest):
        message = str(exc).lower()
        if is_harmless_callback_answer_error(exc):
            return True
        if "message is not modified" in message:
            return True
        if "bot was blocked by the user" in message:
            return True
    return False


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Отвечает на callback, игнорируя просроченные и повторные answer."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        if is_harmless_callback_answer_error(exc):
            logger.debug(
                "callback_answer_skipped callback_id=%s reason=%s",
                callback.id,
                type(exc).__name__,
            )
            return False
        raise
    except TelegramForbiddenError:
        logger.debug(
            "callback_answer_forbidden callback_id=%s user_id=%s",
            callback.id,
            getattr(callback.from_user, "id", None),
        )
        return False


async def ack_callback(callback: CallbackQuery) -> None:
    """Немедленно снимает «часики» у inline-кнопки до тяжёлой обработки."""
    await safe_callback_answer(callback)
