from __future__ import annotations

import logging
from typing import Literal

from aiogram import Bot
from aiogram.types import CallbackQuery, Message

from bot.config import GROUP_ID, OWNER_ID
from bot.database import add_pending_user, get_pending_user, is_member_approved
from bot.keyboards import owner_approval_keyboard
from .views import build_owner_group_member_request_text, build_owner_request_text

logger = logging.getLogger(__name__)

AccessRequestStatus = Literal["created", "exists", "approved"]


def extract_command(message: Message) -> str | None:
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lstrip("/").lower()


async def notify_owner_about_access_request(
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
    in_group: bool = False,
) -> None:
    if OWNER_ID <= 0:
        logger.warning("OWNER_ID не настроен: невозможно отправить заявку владельцу")
        return

    owner_text = (
        build_owner_group_member_request_text(
            user_id=user_id,
            full_name=full_name or "",
            username=username,
        )
        if in_group
        else build_owner_request_text(
            user_id=user_id,
            full_name=full_name or "",
            username=username,
        )
    )

    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=owner_text,
            parse_mode="HTML",
            reply_markup=owner_approval_keyboard(user_id),
        )
    except Exception:
        logger.exception("notify_owner_about_access_request failed user_id=%s", user_id)


async def notify_owner_about_request(callback: CallbackQuery) -> None:
    user = callback.from_user
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    await notify_owner_about_access_request(
        callback.bot,
        user_id=user.id,
        username=user.username,
        full_name=full_name,
        in_group=False,
    )


async def ensure_group_member_access_request(
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    full_name: str | None,
) -> AccessRequestStatus:
    """Создаёт заявку на доступ к боту для участника, уже состоящего в группе."""
    if await is_member_approved(user_id):
        return "approved"
    if await get_pending_user(user_id):
        return "exists"

    await add_pending_user(user_id, username, full_name)
    await notify_owner_about_access_request(
        bot,
        user_id=user_id,
        username=username,
        full_name=full_name,
        in_group=True,
    )
    return "created"


async def notify_owner_about_member_start(message: Message) -> None:
    """Уведомляет владельца, что одобренный участник запустил бота (интро ещё pending)."""
    if OWNER_ID <= 0:
        logger.warning("OWNER_ID не настроен: невозможно уведомить о запуске бота")
        return

    user = message.from_user
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    username = f"@{user.username}" if user.username else "—"
    text = (
        "👋 <b>Участник запустил бота</b>\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {full_name or '—'}\n"
        f"Username: {username}\n\n"
        "Статус «Рассказ о себе»: <b>ожидает</b>.\n"
        "Проверьте подгруппу или отметьте статус через /pending_intro."
    )
    try:
        await message.bot.send_message(chat_id=OWNER_ID, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("notify_owner_about_member_start failed user_id=%s", user.id)


async def is_user_in_group_by_id(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(GROUP_ID, int(user_id))
    except Exception:
        return False
    return member.status in {"member", "administrator", "creator"}


async def is_user_in_group(message: Message, user_id: int | None = None) -> bool:
    target_user_id = int(user_id or message.from_user.id)
    return await is_user_in_group_by_id(message.bot, target_user_id)
