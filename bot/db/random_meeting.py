"""Random meeting opt-in preferences."""

from ._core import _run_query


async def set_random_meeting_opt_in(user_id: int, is_enabled: bool) -> None:
    await _run_query(
        """
        INSERT INTO random_meeting_opt_in (user_id, is_enabled, updated_at)
        VALUES ($user_id, $is_enabled, NOW())
        ON CONFLICT (user_id) DO UPDATE SET is_enabled = EXCLUDED.is_enabled, updated_at = NOW()
        """,
        parameters={"user_id": int(user_id), "is_enabled": bool(is_enabled)},
    )


async def is_random_meeting_opt_in(user_id: int) -> bool:
    result = await _run_query(
        """
        SELECT is_enabled
        FROM random_meeting_opt_in
        WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    if not result[0].rows:
        return False
    return bool(result[0].rows[0].is_enabled)


async def get_random_meeting_opt_in_users() -> list[int]:
    result = await _run_query(
        """
        SELECT r.user_id AS user_id
        FROM random_meeting_opt_in AS r
        INNER JOIN approved_members AS am ON am.user_id = r.user_id
        WHERE r.is_enabled = true
        ORDER BY r.user_id
        """,
    )
    return [row.user_id for row in result[0].rows]
