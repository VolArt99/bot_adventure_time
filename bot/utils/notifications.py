"""Утилиты для ЛС-уведомлений с учётом тихих часов."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz
from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramForbiddenError

from bot.config import QUIET_HOURS_END, QUIET_HOURS_START, TIMEZONE

logger = logging.getLogger(__name__)
_TZ = pytz.timezone(TIMEZONE)


def is_quiet_hours(now: datetime | None = None) -> bool:
    """True, если сейчас тихие часы (ЛС не отправляем сразу)."""
    current = (now or datetime.now(_TZ)).astimezone(_TZ)
    hour = current.hour
    if QUIET_HOURS_START < QUIET_HOURS_END:
        return QUIET_HOURS_START <= hour < QUIET_HOURS_END
    return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END


def next_quiet_hours_end(now: datetime | None = None) -> datetime:
    """Ближайший момент окончания тихих часов в TIMEZONE."""
    current = (now or datetime.now(_TZ)).astimezone(_TZ)
    end = current.replace(
        hour=QUIET_HOURS_END,
        minute=5,
        second=0,
        microsecond=0,
    )
    if QUIET_HOURS_START > QUIET_HOURS_END:
        # Ночной интервал 23→08: если уже после старта или до конца — конец сегодня/завтра утром.
        if current.hour >= QUIET_HOURS_START:
            end = end + timedelta(days=1)
        elif current.hour >= QUIET_HOURS_END and not is_quiet_hours(current):
            end = end + timedelta(days=1)
    else:
        if current >= end:
            end = end + timedelta(days=1)
    return end


async def can_bot_message_user(bot: Bot, user_id: int) -> bool:
    """Проверяет, может ли бот писать пользователю в ЛС (нажат Start)."""
    try:
        await bot.send_chat_action(user_id, ChatAction.TYPING)
        return True
    except TelegramForbiddenError:
        return False


async def get_bot_start_url(bot: Bot) -> str:
    """Возвращает ссылку для запуска бота в ЛС."""
    me = await bot.get_me()
    username = me.username or "bot"
    return f"https://t.me/{username}?start=onboard"


async def send_private_dm(
    bot: Bot,
    user_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
    respect_quiet_hours: bool = True,
    reply_markup=None,
    return_message_id: bool = False,
    queue_if_quiet: bool = True,
    notification_kind: str | None = None,
) -> bool | int | None:
    """Отправляет ЛС; в тихие часы ставит в очередь (если queue_if_quiet).

    ``notification_kind``: ``broadcast`` или ``personal`` — учитывает режим уведомлений пользователя.
    """
    if notification_kind is not None:
        from bot.database import get_user_notification_settings, should_deliver_notification

        mode = await get_user_notification_settings(user_id)
        if not should_deliver_notification(mode, kind=notification_kind):
            logger.info(
                "notification_skipped user_id=%s kind=%s mode=%s",
                user_id,
                notification_kind,
                mode,
            )
            return False
    if respect_quiet_hours and is_quiet_hours():
        if queue_if_quiet:
            from bot.db.pending_notifications import (
                enqueue_pending_notification,
                serialize_inline_keyboard,
            )

            await enqueue_pending_notification(
                user_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                reply_markup_json=serialize_inline_keyboard(reply_markup),
            )
            logger.info("quiet_hours_queued user_id=%s", user_id)
            return True
        logger.info("quiet_hours_skip user_id=%s", user_id)
        return False
    try:
        message = await bot.send_message(
            user_id,
            text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )
        if return_message_id:
            return message.message_id
        return True
    except TelegramForbiddenError:
        logger.info("dm_forbidden user_id=%s", user_id)
        return False
    except Exception:
        logger.exception("dm_failed user_id=%s", user_id)
        return False


async def flush_pending_notifications(bot: Bot, *, limit: int = 100) -> int:
    """Отправляет отложенные ЛС, если сейчас не тихие часы."""
    if is_quiet_hours():
        return 0

    from bot.db.pending_notifications import (
        claim_pending_notifications,
        deserialize_inline_keyboard,
        mark_pending_notification_failed,
        mark_pending_notification_sent,
    )

    claimed = await claim_pending_notifications(limit=limit)
    sent = 0
    for item in claimed:
        try:
            markup = deserialize_inline_keyboard(item.get("reply_markup_json"))
            await bot.send_message(
                int(item["user_id"]),
                str(item["text"]),
                parse_mode=item.get("parse_mode"),
                disable_web_page_preview=bool(item.get("disable_web_page_preview", True)),
                reply_markup=markup,
            )
            await mark_pending_notification_sent(int(item["id"]))
            sent += 1
        except TelegramForbiddenError:
            await mark_pending_notification_failed(int(item["id"]))
        except Exception:
            logger.exception("pending_dm_failed id=%s", item.get("id"))
            await mark_pending_notification_failed(int(item["id"]))
    if claimed:
        logger.info("pending_notifications_flushed claimed=%s sent=%s", len(claimed), sent)
    return sent
