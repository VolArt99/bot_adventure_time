from collections.abc import Callable, Awaitable
from functools import wraps

from aiogram.types import Message, CallbackQuery

from bot.config import RESTRICTED_COMMANDS
from bot.utils.callbacks import finalize_callback
from bot.utils.roles import is_admin_or_owner

EventT = Message | CallbackQuery


def _extract_command(event: EventT) -> str | None:
    if isinstance(event, Message):
        text = event.text or ""
    else:
        text = event.message.text if event.message else ""

    if not text.startswith("/"):
        return None

    command = text.split()[0].split("@")[0].lstrip("/").lower()
    return command


def restricted_command(handler: Callable[..., Awaitable]):
    """Блокирует запуск части команд для не-админов."""

    @wraps(handler)
    async def wrapper(event: EventT, *args, **kwargs):
        user = event.from_user
        if user is None:
            return await handler(event, *args, **kwargs)

        command = _extract_command(event)
        has_extended_access = is_admin_or_owner(user.id)
        if command in RESTRICTED_COMMANDS and not has_extended_access:
            text = "❌ Эта команда доступна только администраторам."
            if isinstance(event, CallbackQuery):
                await finalize_callback(event, text, show_alert=True)
            else:
                await event.answer(text)
            return

        return await handler(event, *args, **kwargs)

    return wrapper
