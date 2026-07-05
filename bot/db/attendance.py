"""Attendance confirmation prompts (24h before event)."""

from datetime import datetime, timezone
from typing import Any

from ._core import _run_query


async def record_attendance_prompts(event_id: int, user_ids: list[int]) -> None:
    now = datetime.now(timezone.utc)
    for user_id in user_ids:
        await _run_query(
            """
            INSERT INTO attendance_responses (event_id, user_id, response, prompted_at)
            VALUES ($event_id, $user_id, 'pending', $prompted_at)
            ON CONFLICT (event_id, user_id) DO UPDATE
            SET response = 'pending', prompted_at = EXCLUDED.prompted_at, responded_at = NULL
            """,
            parameters={
                "event_id": int(event_id),
                "user_id": int(user_id),
                "prompted_at": now,
            },
        )


async def set_attendance_response(event_id: int, user_id: int, response: str) -> bool:
    """Сохраняет ответ confirmed/declined."""
    now = datetime.now(timezone.utc)
    await _run_query(
        """
        INSERT INTO attendance_responses (event_id, user_id, response, prompted_at, responded_at)
        VALUES ($event_id, $user_id, $response, $prompted_at, $responded_at)
        ON CONFLICT (event_id, user_id) DO UPDATE
        SET response = EXCLUDED.response, responded_at = EXCLUDED.responded_at
        """,
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
            "response": response,
            "prompted_at": now,
            "responded_at": now,
        },
    )
    return True


async def get_attendance_summary(event_id: int) -> dict[str, Any]:
    result = await _run_query(
        """
        SELECT response, COUNT(*) AS cnt
        FROM attendance_responses
        WHERE event_id = $event_id
        GROUP BY response
        """,
        parameters={"event_id": int(event_id)},
    )
    summary = {"pending": 0, "confirmed": 0, "declined": 0}
    for row in result[0].rows if result else []:
        summary[str(row.response)] = int(row.cnt)
    return summary
