"""Callback access helpers for actions available only to approved members."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from aiogram.types import CallbackQuery

from bot.database import is_member_approved
from bot.utils.callbacks import finalize_callback


def approved_member_callback_only(handler: Callable[..., Awaitable[Any]]):
    """Decorator that blocks callback actions for non-approved users."""

    @wraps(handler)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        user = callback.from_user
        if not user or not await is_member_approved(user.id):
            await finalize_callback(
                callback,
                "Чтобы записываться на мероприятия, напишите боту /start в личные сообщения "
                "и дождитесь одобрения заявки.",
                show_alert=True,
            )
            return
        return await handler(callback, *args, **kwargs)

    return wrapper
