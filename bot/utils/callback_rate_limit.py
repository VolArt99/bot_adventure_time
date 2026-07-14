"""Shared in-memory rate limit for callback actions."""

from __future__ import annotations

import time

from aiogram.types import CallbackQuery

from bot.utils.telegram_errors import safe_callback_answer

DEFAULT_RATE_LIMIT_SECONDS = 1.5
DEFAULT_CACHE_TTL_SECONDS = 60.0

_hits: dict[tuple[str, int, int, str], float] = {}


def is_callback_rate_limited(
    scope: str,
    user_id: int,
    resource_id: int,
    action: str,
    *,
    cooldown_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
    now: float | None = None,
) -> bool:
    """True if the same (scope, user, resource, action) fired too recently."""
    current_time = time.monotonic() if now is None else now
    if len(_hits) > 2000:
        stale_before = current_time - DEFAULT_CACHE_TTL_SECONDS
        for key, stamped in list(_hits.items()):
            if stamped < stale_before:
                _hits.pop(key, None)

    key = (scope, int(user_id), int(resource_id), action)
    previous = _hits.get(key)
    _hits[key] = current_time
    return bool(previous is not None and current_time - previous < cooldown_seconds)


async def answer_if_callback_rate_limited(
    callback: CallbackQuery,
    *,
    scope: str,
    resource_id: int,
    action: str,
    cooldown_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
) -> bool:
    user = callback.from_user
    if user is None:
        return False
    if not is_callback_rate_limited(
        scope,
        user.id,
        resource_id,
        action,
        cooldown_seconds=cooldown_seconds,
    ):
        return False
    await safe_callback_answer(callback, "⏱ Слишком частые нажатия. Подождите секунду.")
    return True
