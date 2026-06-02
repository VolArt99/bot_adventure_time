from collections.abc import Callable, Awaitable
from functools import wraps
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.utils.callbacks import finalize_callback
from bot.utils.roles import is_admin_or_owner


class IsAdminFilter(BaseFilter):
    """Проверка, что пользователь входит в ADMIN_IDS."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and is_admin_or_owner(user.id))


def admin_only(handler: Callable[..., Awaitable]):
    """Декоратор для централизованной проверки прав админа."""

    @wraps(handler)
    async def wrapper(event: Message | CallbackQuery, *args, **kwargs):
        user = getattr(event, "from_user", None)
        if not user or not is_admin_or_owner(user.id):
            text = "❌ У вас нет прав для выполнения команды."
            if isinstance(event, CallbackQuery):
                await finalize_callback(event, text, show_alert=True)
                return
            await event.answer(text)
            return
        return await handler(event, *args, **kwargs)

    return wrapper
