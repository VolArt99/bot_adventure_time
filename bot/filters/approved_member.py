"""Callback access helpers for actions available only to approved members."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from aiogram.types import CallbackQuery

from bot.database import is_member_approved
from bot.handlers.common_feature.services import ensure_group_member_access_request, is_user_in_group_by_id
from bot.utils.callbacks import finalize_callback
from bot.utils.design import brand_voice


def approved_member_callback_only(handler: Callable[..., Awaitable[Any]]):
    """Decorator that blocks callback actions for non-approved users."""

    @wraps(handler)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        user = callback.from_user
        if not user or not await is_member_approved(user.id):
            if user and await is_user_in_group_by_id(callback.bot, user.id):
                full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
                await ensure_group_member_access_request(
                    callback.bot,
                    user_id=user.id,
                    username=user.username,
                    full_name=full_name,
                )
            await finalize_callback(
                callback,
                brand_voice("approval_required"),
                show_alert=True,
            )
            return
        return await handler(callback, *args, **kwargs)

    return wrapper
