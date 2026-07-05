"""Утилиты для ЛС-уведомлений с учётом тихих часов."""

from __future__ import annotations

import logging
from datetime import datetime

import pytz
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from bot.config import QUIET_HOURS_END, QUIET_HOURS_START, TIMEZONE

logger = logging.getLogger(__name__)
_TZ = pytz.timezone(TIMEZONE)


def is_quiet_hours(now: datetime | None = None) -> bool:
    """True, если сейчас тихие часы (ЛС не отправляем)."""
    current = (now or datetime.now(_TZ)).astimezone(_TZ)
    hour = current.hour
    if QUIET_HOURS_START < QUIET_HOURS_END:
        return QUIET_HOURS_START <= hour < QUIET_HOURS_END
    return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END


async def send_private_dm(
    bot: Bot,
    user_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
    respect_quiet_hours: bool = True,
    reply_markup=None,
) -> bool:
    """Отправляет ЛС; при тихих часах пропускает и возвращает False."""
    if respect_quiet_hours and is_quiet_hours():
        logger.info("quiet_hours_skip user_id=%s", user_id)
        return False
    try:
        await bot.send_message(
            user_id,
            text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )
        return True
    except TelegramForbiddenError:
        logger.info("dm_forbidden user_id=%s", user_id)
        return False
    except Exception:
        logger.exception("dm_failed user_id=%s", user_id)
        return False
