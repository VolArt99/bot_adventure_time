"""Forum topic storage and lookup."""

import asyncio
import logging
from typing import Dict, List, Optional

from ._core import _run_query

logger = logging.getLogger(__name__)


async def get_forum_topics_raw(bot, chat_id: int):
    """
    Возвращает список тем форума из локального хранилища.

    Telegram Bot API не предоставляет стабильного кросс-версийного метода для
    прямого листинга всех тем, поэтому используем обнаруженные/сохранённые темы.
    """
    try:
        chat = await bot.get_chat(chat_id)

        if not getattr(chat, "is_forum", False):
            return []

        stored_topics = await get_all_topics()
        return [
            {
                "message_thread_id": row.get("message_thread_id"),
                "name": row.get("name", f"Тема {row.get('message_thread_id')}"),
                "is_closed": bool(row.get("is_closed", False)),
                "is_hidden": bool(row.get("is_hidden", False)),
            }
            for row in stored_topics
        ]
    except (TypeError, ValueError) as e:
        logger.error("Ошибка при получении тем форума: %s", e)
        return await get_all_topics()


async def save_forum_topic(message_thread_id: int, name: str) -> bool:
    topic_id = int(message_thread_id)
    topic_name = name or f"Тема {message_thread_id}"

    await _run_query(
        """
        INSERT INTO forum_topics (id, message_thread_id, name, is_closed, is_hidden)
        VALUES ($id, $message_thread_id, $name, false, false)
        ON CONFLICT (id) DO UPDATE SET message_thread_id = EXCLUDED.message_thread_id, name = EXCLUDED.name
        """,
        parameters={
            "id": topic_id,
            "message_thread_id": topic_id,
            "name": topic_name,
        },
    )
    return True


async def get_all_topics() -> List[Dict]:
    result = await _run_query(
        """
        SELECT message_thread_id, name, is_closed, is_hidden
        FROM forum_topics
        ORDER BY message_thread_id
        """,
    )
    return [
        {
            "message_thread_id": row.message_thread_id,
            "name": row.name,
            "is_closed": bool(row.is_closed),
            "is_hidden": bool(row.is_hidden),
        }
        for row in result[0].rows
    ]


async def get_topic_by_id(message_thread_id: int) -> Optional[Dict]:
    result = await _run_query(
        """
        SELECT message_thread_id, name, is_closed, is_hidden
        FROM forum_topics
        WHERE message_thread_id = $message_thread_id
        LIMIT 1
        """,
        parameters={"message_thread_id": int(message_thread_id)},
    )
    if not result[0].rows:
        return None
    row = result[0].rows[0]
    return {
        "message_thread_id": row.message_thread_id,
        "name": row.name,
        "is_closed": bool(row.is_closed),
        "is_hidden": bool(row.is_hidden),
    }


async def get_topic_name_by_thread_id(message_thread_id: int | None) -> Optional[str]:
    """Возвращает название темы по её thread_id."""
    if message_thread_id in (None, 0):
        return None
    topic = await get_topic_by_id(int(message_thread_id))
    if not topic:
        return None
    return topic.get("name")


async def resolve_thread_id_by_name_fragment(fragment: str) -> int | None:
    """Ищет message_thread_id по фрагменту названия темы (БД → topics_config)."""
    needle = (fragment or "").strip().lower()
    if not needle:
        return None

    for topic in await get_all_topics():
        name = (topic.get("name") or "").lower()
        if needle in name:
            return int(topic["message_thread_id"])

    try:
        from bot.topics_config import TOPICS_MAPPING

        for thread_id, name in TOPICS_MAPPING.items():
            if needle in str(name).lower():
                return int(thread_id)
    except Exception:
        pass
    return None


async def sync_topics_from_config() -> int:
    try:
        from bot.topics_config import TOPICS_MAPPING
    except Exception:
        return 0

    if not TOPICS_MAPPING:
        return 0

    await asyncio.gather(
        *(save_forum_topic(int(thread_id), str(name)) for thread_id, name in TOPICS_MAPPING.items())
    )
    return len(TOPICS_MAPPING)
