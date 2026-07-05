"""User lookup and creation."""

import logging

from ._core import _run_query

logger = logging.getLogger(__name__)


async def get_or_create_user(user_id: int, username: str = None) -> int:
    """Возвращает пользователя из БД, создаёт если нет."""
    result = await _run_query(
        """
        SELECT id FROM users WHERE id = $user_id
        """,
        parameters={
            "user_id": user_id,
        },
    )

    if not result[0].rows:
        await _run_query(
            """
            INSERT INTO users (id, username) VALUES ($user_id, $username)
            """,
            parameters={
                "user_id": user_id,
                "username": username or "",
            },
        )

    return user_id


async def get_user_id_by_username(username: str) -> int | None:
    """Ищет user_id по username в approved_members/users."""
    normalized = (username or "").strip().lstrip("@").lower()
    if not normalized:
        return None

    async def _query():
        query = """
        SELECT user_id
        FROM approved_members
        WHERE LOWER(COALESCE(username, '')) = $username
        LIMIT 1;
        """
        return await _run_query(query, {"username": normalized})

    try:
        result = await _query()
        rows = result[0].rows
        if rows:
            return int(rows[0].user_id)
    except Exception:
        logger.exception("get_user_id_by_username failed in approved_members")

    async def _query_users():
        query = """
        SELECT id
        FROM users
        WHERE LOWER(COALESCE(username, '')) = $username
        LIMIT 1;
        """
        return await _run_query(query, {"username": normalized})

    try:
        result = await _query_users()
        rows = result[0].rows
        if rows:
            return int(rows[0].id)
    except Exception:
        logger.exception("get_user_id_by_username failed in users")

    return None
