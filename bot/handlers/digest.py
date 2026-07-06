import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from bot.config import GROUP_ID
from bot.database import get_events_for_digest, get_topic_name_by_thread_id
from bot.keyboards import period_keyboard
from bot.texts import format_digest_text
from bot.utils.afisha import build_events_broadcast_text
from bot.utils.helpers import get_username_by_id, build_event_message_link
from bot.utils.callbacks import finalize_callback
from bot.utils.telegram_errors import ack_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE

logger = logging.getLogger(__name__)
router = Router()


async def enrich_events_with_topic_and_links(events: list[dict]) -> list[dict]:
    topic_names = await asyncio.gather(
        *(get_topic_name_by_thread_id(event.get("thread_id")) for event in events)
    )
    enriched_events = []
    for event, topic_name in zip(events, topic_names):
        prepared = dict(event)
        prepared["topic_name"] = topic_name or "Основной чат"
        prepared["event_link"] = build_event_message_link(
            GROUP_ID, event.get("message_id"), event.get("thread_id")
        )
        enriched_events.append(prepared)
    return enriched_events


@router.message(Command("digest"))
async def cmd_digest(message: Message):
    """Ручной запуск дайджеста с выбором периода."""
    await message.answer(
        "Выберите период для дайджеста:",
        reply_markup=period_keyboard("digest_period"),
    )


@router.callback_query(F.data.startswith("digest_period_"))
async def digest_with_period(callback: CallbackQuery):
    await ack_callback(callback)
    period = callback.data.removeprefix("digest_period_")
    events = await get_events_for_digest(period=period)

    if not events:
        await callback.message.answer("📅 На выбранный период мероприятий не запланировано.")
        await finalize_callback(
            callback,
            delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
            skip_answer=True,
        )
        return

    creator_ids = sorted({e["creator_id"] for e in events})
    resolved_names = await asyncio.gather(
        *(get_username_by_id(cid, callback.bot) for cid in creator_ids)
    )
    usernames = {
        cid: (name or str(cid))
        for cid, name in zip(creator_ids, resolved_names)
    }

    enriched_events = await enrich_events_with_topic_and_links(events)
    text = format_digest_text(enriched_events, usernames, period=period)
    await callback.message.answer(text, parse_mode="HTML")
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )


async def send_digest(bot, chat_id: int, thread_id: int = None):
    """Автоматическая отправка еженедельной афиши."""
    try:
        text = await build_events_broadcast_text("week")
        if text.startswith("📭"):
            return

        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info("Дайджест отправлен (thread_id=%s)", thread_id)
    except Exception as e:
        logger.error(f"Ошибка отправки дайджеста: {e}")
