"""Pending and approved member management."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ._core import _normalize_row, _parse_event_datetime, _run_query

logger = logging.getLogger(__name__)


async def add_pending_user(user_id: int, username: str | None, full_name: str | None) -> None:
    await _run_query(
        """
        INSERT INTO pending_users (user_id, username, full_name, status, created_at)
        VALUES ($user_id, $username, $full_name, $status, NOW())
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, status = EXCLUDED.status
        """,
        parameters={
            "user_id": int(user_id),
            "username": username or "",
            "full_name": full_name or "",
            "status": "waiting_approval",
        },
    )


async def get_pending_user(user_id: int) -> Optional[Dict[str, Any]]:
    result = await _run_query(
        """
        SELECT user_id, username, full_name, status, created_at
        FROM pending_users
        WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def delete_pending_user(user_id: int) -> None:
    await _run_query(
        """
        DELETE FROM pending_users WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )


async def is_member_approved(user_id: int) -> bool:
    result = await _run_query(
        """
        SELECT user_id FROM approved_members WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    return bool(result[0].rows)


async def get_approved_member(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает запись одобренного участника или None."""
    result = await _run_query(
        """
        SELECT user_id, username, full_name, join_date, intro_status
        FROM approved_members
        WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def approve_pending_user(user_id: int) -> Optional[Dict[str, Any]]:
    pending = await get_pending_user(user_id)
    if not pending:
        return None
    await _run_query(
        """
        INSERT INTO approved_members (user_id, username, full_name, intro_status)
        VALUES ($user_id, $username, $full_name, $intro_status)
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, intro_status = EXCLUDED.intro_status
        """,
        parameters={
            "user_id": int(user_id),
            "username": str(pending.get("username") or ""),
            "full_name": str(pending.get("full_name") or ""),
            "intro_status": "pending",
        },
    )
    await delete_pending_user(user_id)
    return pending


async def upsert_approved_member(
    user_id: int,
    username: str | None,
    full_name: str | None,
    *,
    intro_status: str = "completed",
) -> None:
    await _run_query(
        """
        INSERT INTO approved_members (user_id, username, full_name, intro_status)
        VALUES ($user_id, $username, $full_name, $intro_status)
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, intro_status = EXCLUDED.intro_status
        """,
        parameters={
            "user_id": int(user_id),
            "username": str(username or ""),
            "full_name": str(full_name or ""),
            "intro_status": intro_status,
        },
    )


async def delete_approved_member(user_id: int) -> None:
    await _run_query(
        """
        DELETE FROM approved_members
        WHERE user_id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )


async def get_pending_intro_members() -> list[Dict[str, Any]]:
    result = await _run_query(
        """
        SELECT user_id, username, full_name, join_date, intro_status
        FROM approved_members
        WHERE intro_status = 'pending'
        ORDER BY join_date
        """,
    )
    return [_normalize_row(row) for row in result[0].rows]


async def get_intro_members_statuses() -> list[Dict[str, Any]]:
    result = await _run_query(
        """
        SELECT user_id, username, full_name, join_date, intro_status
        FROM approved_members
        ORDER BY join_date
        """,
    )
    return [_normalize_row(row) for row in result[0].rows]


async def get_approved_member_ids() -> list[int]:
    result = await _run_query(
        """
        SELECT user_id
        FROM approved_members
        """,
    )
    return [int(row.user_id) for row in (result[0].rows if result else [])]


async def update_intro_status(user_id: int, intro_status: str) -> None:
    await _run_query(
        """
        UPDATE approved_members SET intro_status = $intro_status
        WHERE user_id = $user_id
        """,
        parameters={
            "user_id": int(user_id),
            "intro_status": intro_status,
        },
    )


async def get_member_reengage_candidates(days_inactive: int = 30) -> list[Dict[str, Any]]:
    """Возвращает одобренных участников с датой последнего участия в прошедших мероприятиях."""
    result = await _run_query(
        """
        SELECT
            am.user_id AS user_id,
            am.username AS username,
            am.full_name AS full_name,
            am.join_date AS join_date,
            MAX(e.date_time) AS last_event_date
        FROM approved_members AS am
        LEFT JOIN participants AS p ON p.user_id = am.user_id
        LEFT JOIN events AS e ON e.id = p.event_id
        GROUP BY am.user_id, am.username, am.full_name, am.join_date
        """,
    )

    now = datetime.now(timezone.utc)
    items: list[Dict[str, Any]] = []
    for row in result[0].rows:
        record = _normalize_row(row)
        last_event_date = _parse_event_datetime(record.get("last_event_date"))
        if last_event_date is not None:
            if last_event_date.tzinfo is None:
                last_event_date = last_event_date.replace(tzinfo=timezone.utc)
            if last_event_date > now:
                continue
            inactive_days = (now - last_event_date).days
        else:
            join_date = _parse_event_datetime(record.get("join_date"))
            if join_date is not None and join_date.tzinfo is None:
                join_date = join_date.replace(tzinfo=timezone.utc)
            baseline = join_date or now
            inactive_days = (now - baseline).days

        if inactive_days < days_inactive:
            continue
        record["inactive_days"] = inactive_days
        record["last_event_date"] = last_event_date.isoformat() if last_event_date else None
        items.append(record)

    items.sort(key=lambda x: int(x.get("inactive_days", 0)), reverse=True)
    return items
