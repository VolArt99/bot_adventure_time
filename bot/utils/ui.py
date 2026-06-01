from __future__ import annotations
import asyncio
import logging
from collections.abc import Mapping
from html import escape
from aiogram import Bot

logger = logging.getLogger(__name__)
from aiogram.fsm.context import FSMContext

PRIVATE_INTERMEDIATE_MESSAGE_IDS_KEY = "private_intermediate_message_ids"


def quote_block(title: str, body_lines: list[str], *, allow_html: bool = False) -> str:
    safe_title = escape(title)
    safe_body = "\n".join((x if allow_html else escape(x)) for x in body_lines if x)
    return f"<blockquote><b>{safe_title}</b>\n{safe_body}</blockquote>"


def ok(text: str) -> str:
    return f"✅ {text}"


def err(text: str) -> str:
    return f"❌ {text}"


async def safe_delete_bot_message(message) -> None:
    """Удаляет сообщение только если оно отправлено ботом."""
    try:
        if message and message.from_user and bool(getattr(message.from_user, "is_bot", False)):
            await message.delete()
    except Exception as exc:
        logger.debug("Не удалось удалить сообщение бота: %s", exc)


async def safe_delete_message_by_id(bot: Bot, chat_id: int, message_id: int) -> None:
    """Best-effort удаление сообщения по id."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.debug("Не удалось удалить сообщение chat_id=%s message_id=%s: %s", chat_id, message_id, exc)


def is_private_message(message) -> bool:
    """Возвращает True, если сообщение находится в личном чате."""
    return bool(message and getattr(getattr(message, "chat", None), "type", None) == "private")


async def cleanup_private_intermediate_messages(message, state: FSMContext) -> None:
    """Удаляет сохранённые промежуточные сообщения бота в личном чате.

    Используется FSM-сценариями: перед отправкой следующего шага или итогового
    ответа удаляются предыдущие подсказки/ошибки бота. Итоговые сообщения не
    сохраняются через этот helper и поэтому остаются в переписке.
    """
    if not is_private_message(message):
        return

    data: Mapping = await state.get_data()
    message_ids = data.get(PRIVATE_INTERMEDIATE_MESSAGE_IDS_KEY) or []
    if not message_ids:
        return

    chat_id = message.chat.id
    bot = message.bot
    for message_id in dict.fromkeys(int(mid) for mid in message_ids if mid):
        await safe_delete_message_by_id(bot, chat_id, message_id)
    await state.update_data(**{PRIVATE_INTERMEDIATE_MESSAGE_IDS_KEY: []})


async def answer_private_intermediate(message, state: FSMContext, *args, **kwargs):
    """Отправляет промежуточное сообщение FSM-сценария и запоминает его для удаления."""
    await cleanup_private_intermediate_messages(message, state)
    sent = await message.answer(*args, **kwargs)
    if is_private_message(message) and sent:
        await state.update_data(**{PRIVATE_INTERMEDIATE_MESSAGE_IDS_KEY: [sent.message_id]})
    return sent


async def answer_private_final(message, state: FSMContext, *args, **kwargs):
    """Удаляет промежуточные сообщения и отправляет финальный ответ, не помечая его на удаление."""
    await cleanup_private_intermediate_messages(message, state)
    return await message.answer(*args, **kwargs)

    
def info(text: str) -> str:
    return f"ℹ️ {text}"


async def delete_message_later(bot: Bot, chat_id: int, message_id: int, ttl_seconds: int = 20) -> None:
    await asyncio.sleep(max(1, ttl_seconds))
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.debug("Не удалось отложенно удалить сообщение chat_id=%s message_id=%s: %s", chat_id, message_id, exc)
        return
