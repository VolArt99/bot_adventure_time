"""User and admin statistics."""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from ._core import _run_query


async def get_user_stats(user_id: int) -> Dict:
    """⚠️ НОВОЕ: Возвращает статистику пользователя."""
    result_creator = await _run_query(
        """
        SELECT COUNT(*) as events_count FROM events
        WHERE creator_id = $user_id AND status = 'active'
        """,
        parameters={
            "user_id": user_id,
        },
    )

    events_count = (
        result_creator[0].rows[0].events_count if result_creator[0].rows else 0
    )

    result_participations = await _run_query(
        """
        SELECT COUNT(DISTINCT event_id) as total_participations FROM participants
        WHERE user_id = $user_id
        """,
        parameters={
            "user_id": user_id,
        },
    )

    total_participations = (
        result_participations[0].rows[0].total_participations
        if result_participations[0].rows
        else 0
    )

    return {
        "events_count": events_count,
        "total_participations": total_participations,
    }


async def get_admin_report_metrics() -> Dict[str, Any]:
    """Возвращает агрегированные метрики для команды /admin_report."""
    active_events_result = await _run_query(
        """
        SELECT COUNT(*) AS active_events
        FROM events
        WHERE status = 'active'
        """,
    )
    active_events = (
        int(active_events_result[0].rows[0].active_events)
        if active_events_result and active_events_result[0].rows
        else 0
    )

    attendance_result = await _run_query(
        """
        SELECT COUNT(*) AS attendance_count
        FROM events e
        JOIN participants p ON e.id = p.event_id
        WHERE e.status = 'active'
          AND p.status IN ('going', 'driver', 'passenger')
        """,
    )
    attendance_count = (
        int(attendance_result[0].rows[0].attendance_count)
        if attendance_result and attendance_result[0].rows
        else 0
    )
    avg_attendance = round(attendance_count / active_events, 2) if active_events else 0.0

    top_categories_result = await _run_query(
        """
        SELECT category, COUNT(*) AS cnt
        FROM events
        WHERE status = 'active'
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 5
        """,
    )

    top_categories: List[Dict[str, Any]] = []
    for row in top_categories_result[0].rows if top_categories_result else []:
        category_name = (row.category or 'Без категории').strip() if isinstance(row.category, str) else 'Без категории'
        top_categories.append({'category': category_name, 'cnt': int(row.cnt)})

    return {
        'active_events': active_events,
        'avg_attendance': avg_attendance,
        'top_categories': top_categories,
    }


async def get_top_participants(days: int = 30, limit: int = 3) -> List[Dict]:
    """Топ участников по количеству участий за период."""
    safe_days = max(0, int(days))
    cutoff_ts = datetime.utcnow() - timedelta(days=safe_days)

    result = await _run_query(
        """
        SELECT
            p.user_id,
            u.username,
            COUNT(DISTINCT p.event_id) as participation_count
        FROM participants p
        LEFT JOIN users u ON p.user_id = u.id
        WHERE p.joined_at >= $cutoff_ts
        GROUP BY p.user_id, u.username
        ORDER BY participation_count DESC
        LIMIT $limit
        """,
        parameters={
            "cutoff_ts": cutoff_ts,
            "limit": int(limit),
        },
    )

    top_participants = []
    for row in result[0].rows:
        top_participants.append(
            {
                "user_id": row.user_id,
                "username": row.username or f"User {row.user_id}",
                "participations": int(row.participation_count or 0),
            }
        )

    return top_participants
