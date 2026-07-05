"""User category subscriptions."""

import logging

from ._core import _run_query

logger = logging.getLogger(__name__)


async def set_user_category_subscriptions(user_id: int, categories: list[str]) -> None:
    """Перезаписывает список подписок пользователя по категориям."""
    await _run_query(
        """
        DELETE FROM user_category_subscriptions WHERE user_id = $user_id
        """,
        parameters={
            "user_id": user_id,
        },
    )

    for category in categories:
        if category.strip():
            await _run_query(
                """
                INSERT INTO user_category_subscriptions (user_id, category)
                VALUES ($user_id, $category)
                """,
                parameters={
                    "user_id": user_id,
                    "category": category.strip(),
                },
            )

    logger.info(f"Обновлены подписки пользователя {user_id}: {categories}")


async def get_user_category_subscriptions(user_id: int) -> list[str]:
    """Возвращает категории, на которые подписан пользователь."""
    result = await _run_query(
        """
        SELECT category FROM user_category_subscriptions
        WHERE user_id = $user_id
        ORDER BY category
        """,
        parameters={
            "user_id": user_id,
        },
    )

    return [row.category for row in result[0].rows]


async def get_users_subscribed_to_categories(categories: list[str]) -> list[int]:
    normalized = [category.strip() for category in categories if category and category.strip()]
    if not normalized:
        return []

    result = await _run_query(
        """
        SELECT DISTINCT user_id
        FROM user_category_subscriptions
        WHERE category = ANY($categories)
        ORDER BY user_id
        """,
        parameters={"categories": normalized},
    )
    return [int(row.user_id) for row in result[0].rows]
