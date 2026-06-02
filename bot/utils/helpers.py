import asyncio
import logging
import re
import time
from html import escape
from urllib.parse import quote, urlparse

from aiogram import Bot

logger = logging.getLogger(__name__)
USER_MENTION_CACHE_TTL_SECONDS = 3600
_user_mentions_cache: dict[int, tuple[float, str]] = {}
_TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def build_event_message_link(chat_id: int, message_id: int | None) -> str | None:
    """Строит ссылку на сообщение в супергруппе/форуме Telegram."""
    if not message_id:
        return None

    chat_str = str(chat_id)
    if chat_str.startswith("-100"):
        chat_part = chat_str[4:]
    elif chat_str.startswith("-"):
        chat_part = chat_str[1:]
    else:
        chat_part = chat_str

    return f"https://t.me/c/{chat_part}/{message_id}"


def _strip_control_chars(value: str) -> str:
    """Удаляет управляющие символы, которые не должны попадать в HTML/URL."""
    return "".join(ch for ch in value if ch >= " " and ch != "\x7f").strip()


def build_owner_contact_html(owner_contact: str | None, owner_id: int, *, label: str = "владельцу") -> str:
    """Возвращает безопасный HTML-контакт владельца для сообщений Telegram."""
    safe_label = escape(_strip_control_chars(label) or "владельцу")
    contact = _strip_control_chars(owner_contact or "")

    if contact.startswith("@"):
        username = contact[1:]
        if _TELEGRAM_USERNAME_RE.fullmatch(username):
            return f'<a href="https://t.me/{quote(username)}">{safe_label}</a>'
        return escape(contact)

    if contact.startswith("https://"):
        parsed = urlparse(contact)
        if parsed.scheme == "https" and parsed.netloc:
            safe_url = escape(contact, quote=True)
            return f'<a href="{safe_url}">{safe_label}</a>'
        return escape(contact)

    if contact:
        return escape(contact)

    if owner_id > 0:
        return f'<a href="tg://user?id={int(owner_id)}">{safe_label}</a>'
    return safe_label


async def get_username_by_id(user_id: int, bot: Bot) -> str | None:
    """Возвращает username или имя пользователя."""
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return chat.username
        full_name = " ".join(filter(None, [chat.first_name, getattr(chat, "last_name", None)])).strip()
        return full_name or None
    except Exception as exc:
        logger.debug("Не удалось получить username для user_id=%s: %s", user_id, exc)


async def get_user_mention(user_id: int, bot: Bot) -> str:
    """Возвращает HTML-mention для Telegram с коротким in-memory кешем."""
    now = time.monotonic()
    cached = _user_mentions_cache.get(int(user_id))
    if cached and now - cached[0] < USER_MENTION_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            mention = f"@{escape(chat.username)}"
        else:
            full_name = " ".join(
                filter(None, [chat.first_name, getattr(chat, "last_name", None)])
            ).strip() or f"id{user_id}"
            mention = f'<a href="tg://user?id={user_id}">{escape(full_name)}</a>'
    except Exception as exc:
        logger.debug("Не удалось получить mention для user_id=%s: %s", user_id, exc)
        mention = f'<a href="tg://user?id={user_id}">id{user_id}</a>'

    _user_mentions_cache[int(user_id)] = (now, mention)
    return mention


async def get_user_mentions(user_ids: set[int] | list[int] | tuple[int, ...], bot: Bot) -> dict[int, str]:
    """Параллельно собирает HTML-mentions для набора пользователей."""
    normalized_ids = sorted({int(uid) for uid in user_ids if uid is not None})
    mentions = await asyncio.gather(*(get_user_mention(uid, bot) for uid in normalized_ids))
    return dict(zip(normalized_ids, mentions))


def parse_int_arg(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value.isdigit():
        return None
    return int(value)