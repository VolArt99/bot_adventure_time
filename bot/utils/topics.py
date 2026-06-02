import logging

from bot.database import get_topic_by_id, save_forum_topic

logger = logging.getLogger(__name__)


def get_topics_list_from_config() -> list[dict]:
    """Список тем для выбора в UI — только из topics_config.py."""
    try:
        from bot.topics_config import TOPICS_MAPPING
    except Exception:
        return []

    return [
        {"message_thread_id": int(thread_id), "name": str(name)}
        for thread_id, name in sorted(
            TOPICS_MAPPING.items(),
            key=lambda item: str(item[1]).casefold(),
        )
    ]


async def get_topics_list_from_db() -> list:
    """Получает список тем для выбора (только topics_config.py)."""
    topics = get_topics_list_from_config()
    logger.info("Загружено %s тем из topics_config", len(topics))
    return topics


async def validate_thread_id(thread_id: int | None) -> bool:
    """Проверяет, что тема объявлена в topics_config.py."""
    if thread_id in (None, 0):
        return True

    try:
        from bot.topics_config import TOPICS_MAPPING
    except Exception:
        return False

    return int(thread_id) in TOPICS_MAPPING

async def update_topic_name(thread_id: int, name: str) -> bool:
    """Обновляет/добавляет тему в БД."""
    return await save_forum_topic(thread_id, name)