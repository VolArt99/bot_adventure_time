"""Форматирование афиши мероприятий для публикации в группе."""

from datetime import datetime

import pytz

from bot.config import GROUP_ID, TIMEZONE
from bot.database import get_events_for_digest
from bot.texts import format_event_period
from bot.utils.design import brand_voice
from bot.utils.helpers import build_event_message_link
from bot.utils.ui import quote_block

TZ = pytz.timezone(TIMEZONE)


async def build_events_broadcast_text(period: str) -> str:
    """Собирает HTML-текст афиши в едином формате (ручная и автоматическая отправка)."""
    events = await get_events_for_digest(period=period)
    period_title = {"week": "неделю", "month": "месяц", "all": "всё время"}.get(period, "период")
    if not events:
        return f"📭 На ближайшее {period_title} активных мероприятий нет."

    lines = [quote_block(f"🗓 Актуальная афиша на {period_title}", [])]
    has_event_links = False
    for event in events:
        dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
        period_text = format_event_period(dt, event.get("period_end"))
        date_line = period_text or f"🗓 {dt.strftime('%d.%m.%Y %H:%M')}"
        event_link = build_event_message_link(
            GROUP_ID, event.get("message_id"), event.get("thread_id")
        )
        if event_link:
            has_event_links = True
        link_text = f'<a href="{event_link}">открыть сообщение</a>' if event_link else "недоступна"
        lines.append(
            quote_block(
                str(event["title"]),
                [
                    date_line,
                    f"📍 {event.get('location') or 'не указано'}",
                    f"🆔 {event['id']}",
                    f"🔗 {link_text}",
                ],
                allow_html=True,
            )
        )
    if has_event_links:
        lines.append(
            quote_block(
                brand_voice("afisha_iphone_hint_title"),
                [brand_voice("afisha_iphone_hint_body")],
            )
        )
    return "\n".join(lines)
