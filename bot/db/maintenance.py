"""Periodic DB maintenance helpers."""

from __future__ import annotations

from ._core import _run_query


async def cleanup_stale_fsm_states(days: int = 7) -> int:
    """Removes FSM rows older than N days (including cleared empty rows)."""
    result = await _run_query(
        """
        DELETE FROM fsm_states
        WHERE updated_at IS NULL
           OR updated_at < NOW() - ($days || ' days')::interval
           OR (
                state IS NULL
                AND (data_json IS NULL OR data_json IN ('', '{}'))
                AND COALESCE(updated_at, NOW()) < NOW() - INTERVAL '1 day'
           )
        RETURNING user_id
        """,
        parameters={"days": int(days)},
    )
    return len(result[0].rows)
