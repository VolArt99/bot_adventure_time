"""Daily birthday greetings in the community topic."""

from __future__ import annotations

import logging
from datetime import datetime

import pytz
from aiogram import Bot

from bot.config import BIRTHDAY_THREAD_ID, BIRTHDAY_TOPIC_NAME, GROUP_ID, TIMEZONE
from bot.db.birthdays import (
    get_approved_members_with_birthday_on,
    record_birthday_greeting,
    was_birthday_greeted,
)
from bot.db.topics import resolve_thread_id_by_name_fragment
from bot.utils.design import brand_voice
from bot.utils.helpers import get_user_mention

logger = logging.getLogger(__name__)
_TZ = pytz.timezone(TIMEZONE)


async def resolve_birthday_thread_id() -> int | None:
    """Resolves thread_id for birthday posts (env → DB name → topics_config)."""
    if BIRTHDAY_THREAD_ID:
        return int(BIRTHDAY_THREAD_ID)
    return await resolve_thread_id_by_name_fragment(BIRTHDAY_TOPIC_NAME)


async def send_daily_birthday_greetings(bot: Bot) -> int:
    """Posts birthday greetings to the configured topic. Returns count greeted."""
    if not GROUP_ID:
        logger.warning("birthday_skip group_id_missing")
        return 0

    thread_id = await resolve_birthday_thread_id()
    if not thread_id:
        logger.warning(
            "birthday_skip thread_not_found topic_name=%r thread_id_env=%s",
            BIRTHDAY_TOPIC_NAME,
            BIRTHDAY_THREAD_ID,
        )
        return 0

    today = datetime.now(_TZ).date()
    mm_dd = today.strftime("%m-%d")
    members = await get_approved_members_with_birthday_on(mm_dd)
    if not members:
        logger.info("birthday_none today=%s", mm_dd)
        return 0

    pending: list[dict] = []
    for member in members:
        user_id = int(member["user_id"])
        if await was_birthday_greeted(user_id, today):
            continue
        pending.append(member)

    if not pending:
        logger.info("birthday_already_greeted today=%s total=%s", mm_dd, len(members))
        return 0

    mention_lines: list[str] = []
    for member in pending:
        user_id = int(member["user_id"])
        mention = await get_user_mention(user_id, bot)
        mention_lines.append(f"• {mention}")

    if len(pending) == 1:
        intro = brand_voice("birthday_post_single")
    else:
        intro = brand_voice("birthday_post_many").format(count=len(pending))

    text = f"{intro}\n" + "\n".join(mention_lines) + f"\n\n{brand_voice('birthday_post_footer')}"

    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=int(thread_id),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception(
            "birthday_post_failed thread_id=%s recipients=%s",
            thread_id,
            len(pending),
        )
        return 0

    for member in pending:
        await record_birthday_greeting(int(member["user_id"]), today)

    logger.info(
        "birthday_post_sent thread_id=%s recipients=%s topic=%r",
        thread_id,
        len(pending),
        BIRTHDAY_TOPIC_NAME,
    )
    return len(pending)
