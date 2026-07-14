"""Push-уведомления подписчикам при публикации нового мероприятия."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot

from bot.config import GROUP_ID
from bot.database import get_users_subscribed_to_categories
from bot.utils.helpers import build_event_message_link
from bot.utils.notifications import send_private_dm

logger = logging.getLogger(__name__)


def _parse_event_categories(category_value: str | None) -> list[str]:
    if not category_value:
        return []
    return [item.strip() for item in str(category_value).split(",") if item.strip()]


async def notify_category_subscribers(
    bot: Bot,
    *,
    event_id: int,
    title: str,
    category_value: str | None,
    creator_id: int,
    message_id: int | None,
    thread_id: int | None,
) -> int:
    """Рассылает ЛС подписчикам категорий. Возвращает число успешных отправок."""
    categories = _parse_event_categories(category_value)
    if not categories:
        return 0

    user_ids = await get_users_subscribed_to_categories(categories)
    if not user_ids:
        return 0

    link = build_event_message_link(GROUP_ID, message_id, thread_id)
    link_line = f'<a href="{link}">открыть карточку</a>' if link else "смотрите афишу в группе"
    safe_title = escape(str(title))
    categories_text = escape(", ".join(categories))
    text = (
        "🔔 <b>Новое мероприятие по твоей подписке</b>\n"
        f"• <b>{safe_title}</b>\n"
        f"• Категории: {categories_text}\n"
        f"• {link_line}"
    )

    sent = 0
    for user_id in user_ids:
        if int(user_id) == int(creator_id):
            continue
        if await send_private_dm(bot, int(user_id), text, notification_kind="broadcast"):
            sent += 1
    logger.info(
        "category_push event_id=%s categories=%s recipients=%s sent=%s",
        event_id,
        categories,
        len(user_ids),
        sent,
    )
    return sent
