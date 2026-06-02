from __future__ import annotations

import logging
from aiogram.types import CallbackQuery, Message

from bot.config import GROUP_ID, OWNER_ID
from bot.keyboards import owner_approval_keyboard
from .views import build_owner_request_text

logger = logging.getLogger(__name__)


def extract_command(message: Message) -> str | None:
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lstrip("/").lower()


async def notify_owner_about_request(callback: CallbackQuery) -> None:
    user = callback.from_user
    if OWNER_ID <= 0:
        logger.warning("OWNER_ID не настроен: невозможно отправить заявку владельцу")
        return

    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    owner_text = build_owner_request_text(
        user_id=user.id,
        full_name=full_name,
        username=user.username,
    )

    await callback.bot.send_message(
        chat_id=OWNER_ID,
        text=owner_text,
        parse_mode="HTML",
        reply_markup=owner_approval_keyboard(user.id),
    )


async def is_user_in_group(message: Message, user_id: int | None = None) -> bool:
    target_user_id = int(user_id or message.from_user.id)
    try:
        member = await message.bot.get_chat_member(GROUP_ID, target_user_id)
    except Exception:
        return False
    return member.status in {"member", "administrator", "creator"}
