"""Event CRUD and queries."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .subscriptions import get_user_category_subscriptions
from ._core import (
    _event_matches_period_filter,
    _normalize_row,
    _period_to_days,
    _run_query,
)


async def create_event(event_data: Dict[str, Any]) -> int:
    """Создаёт мероприятие и возвращает его ID."""
    event_id = int(time.time() * 1000)

    await _run_query(
        """
        INSERT INTO events (
            id, title, description, date_time, duration_minutes, period_end,
            location,
            price_total, price_per_person, participant_limit,
            thread_id, message_id, creator_id,
            responsible_id, weather_info, carpool_enabled, category
        ) VALUES (
            $id, $title, $description, $date_time, $duration_minutes, $period_end,
            $location,
            $price_total, $price_per_person, $participant_limit,
            $thread_id, $message_id, $creator_id,
            $responsible_id, $weather_info, $carpool_enabled, $category
        )
        """,
        parameters={
            "id": event_id,
            "title": event_data.get("title", ""),
            "description": event_data.get("description", ""),
            "date_time": event_data.get("date_time", ""),
            "duration_minutes": event_data.get("duration_minutes") or 0,
            "period_end": event_data.get("period_end") or "",
            "location": event_data.get("location", ""),
            "price_total": event_data.get("price_total") or 0.0,
            "price_per_person": event_data.get("price_per_person") or 0.0,
            "participant_limit": event_data.get("participant_limit") or 0,
            "thread_id": event_data.get("thread_id") or 0,
            "message_id": event_data.get("message_id") or 0,
            "creator_id": event_data.get("creator_id", 0),
            "responsible_id": event_data.get("responsible_id") or event_data.get("creator_id", 0),
            "weather_info": event_data.get("weather_info", ""),
            "carpool_enabled": bool(event_data.get("carpool_enabled", False)),
            "category": event_data.get("category", ""),
        },
    )

    return event_id


async def get_event(event_id: int) -> Optional[Dict]:
    """Возвращает мероприятие по ID."""
    result = await _run_query(
        """
        SELECT * FROM events WHERE id = $event_id
        """,
        parameters={
            "event_id": event_id,
        },
    )

    if not result[0].rows:
        return None

    row = result[0].rows[0]
    return _normalize_row(row)


async def update_event_message_id(event_id: int, thread_id: int, message_id: int):
    """Сохраняет thread_id и message_id после публикации."""
    await _run_query(
        """
        UPDATE events SET thread_id = $thread_id, message_id = $message_id
        WHERE id = $event_id
        """,
        parameters={
            "event_id": event_id,
            "thread_id": thread_id or 0,
            "message_id": message_id,
        },
    )


async def update_event(event_id: int, fields: Dict[str, Any]) -> bool:
    """Обновляет поля мероприятия. Возвращает False, если событие не найдено."""
    allowed = {
        "title", "description", "date_time", "duration_minutes", "period_end",
        "location", "price_total", "price_per_person", "participant_limit",
        "thread_id", "weather_info", "carpool_enabled", "category",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return bool(await get_event(event_id))

    set_clause = ", ".join(f"{column} = ${column}" for column in updates)
    parameters = {"event_id": int(event_id), **updates}
    await _run_query(
        f"UPDATE events SET {set_clause} WHERE id = $event_id",
        parameters=parameters,
    )
    return bool(await get_event(event_id))


async def get_active_events() -> List[Dict]:
    """Возвращает все активные мероприятия."""
    result = await _run_query(
        """
        SELECT * FROM events
        WHERE status = 'active'
        ORDER BY date_time
        """,
    )

    return [_normalize_row(row) for row in result[0].rows]


async def cancel_event(event_id: int) -> None:
    """Помечает мероприятие как отменённое и очищает участников."""
    await _run_query(
        """
        UPDATE events SET status = 'cancelled' WHERE id = $event_id
        """,
        parameters={
            "event_id": event_id,
        },
    )

    await _run_query(
        """
        DELETE FROM participants WHERE event_id = $event_id
        """,
        parameters={
            "event_id": event_id,
        },
    )


async def find_events(query: str, period: str = "month", limit: int = 20) -> List[Dict]:
    """Поиск предстоящих активных мероприятий по названию/месту/категории."""
    period_days = _period_to_days(period, default_days=30)
    result = await _run_query(
        """
        SELECT * FROM events
        WHERE status = 'active'
        AND (
            title LIKE '%' || $query || '%'
            OR location LIKE '%' || $query || '%'
            OR category LIKE '%' || $query || '%'
            OR description LIKE '%' || $query || '%'
        )
        ORDER BY date_time
        """,
        parameters={
            "query": query,
        },
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    events: List[Dict] = []

    for row in result[0].rows:
        event_dict = _normalize_row(row)
        if _event_matches_period_filter(event_dict, now, max_dt):
            events.append(event_dict)

    events.sort(key=lambda x: x.get("date_time", ""))
    return events[:limit]


async def get_user_events(user_id: int, status: str = None) -> List[Dict]:
    """Возвращает мероприятия пользователя: как участника и/или организатора."""
    if status == "organizer":
        query = """
            SELECT e.* FROM events e
            WHERE e.creator_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    elif status == "participant":
        query = """
            SELECT DISTINCT e.* FROM events e
            JOIN participants p ON e.id = p.event_id
            WHERE p.user_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    else:
        query = """
            SELECT * FROM events
            WHERE (
                creator_id = $user_id
                OR id IN (
                    SELECT event_id FROM participants
                    WHERE user_id = $user_id
                )
            )
            AND status = 'active'
            ORDER BY date_time
        """
        params = {"user_id": user_id}

    result = await _run_query(
        query,
        parameters=params,
    )

    return [_normalize_row(row) for row in result[0].rows]


async def update_event_status(event_id: int, status: str):
    """Обновляет статус мероприятия."""
    await _run_query(
        """
        UPDATE events SET status = $status WHERE id = $event_id
        """,
        parameters={
            "event_id": event_id,
            "status": status,
        },
    )


async def set_event_responsible(event_id: int, responsible_id: int) -> None:
    """Назначает ответственного за мероприятие."""
    await _run_query(
        """
        UPDATE events
        SET responsible_id = $responsible_id
        WHERE id = $event_id
        """,
        parameters={
            "event_id": int(event_id),
            "responsible_id": int(responsible_id),
        },
    )


async def get_events_for_digest(period: str = "week") -> List[Dict]:
    """Получение предстоящих активных мероприятий для дайджеста."""
    period_days = _period_to_days(period)
    result = await _run_query(
        """
        SELECT * FROM events
        WHERE status = 'active'
        ORDER BY date_time
        """,
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    events: List[Dict] = []
    for row in result[0].rows:
        event_dict = _normalize_row(row)
        if _event_matches_period_filter(event_dict, now, max_dt):
            events.append(event_dict)

    event_ids = {int(event["id"]) for event in events}
    if event_ids:
        counts_result = await _run_query(
            """
            SELECT event_id, status FROM participants
            """,
        )
        counts: dict[int, dict[str, int]] = {event_id: {"going": 0, "waitlist": 0} for event_id in event_ids}
        for row in counts_result[0].rows:
            if not hasattr(row, "event_id"):
                continue
            event_id = int(row.event_id)
            if event_id not in counts:
                continue
            status = str(row.status)
            if status in {"going", "driver", "passenger"}:
                counts[event_id]["going"] += 1
            elif status == "waitlist":
                counts[event_id]["waitlist"] += 1
        for event in events:
            event_counts = counts.get(int(event["id"]), {})
            event["going_count"] = event_counts.get("going", 0)
            event["waitlist_count"] = event_counts.get("waitlist", 0)

    events.sort(key=lambda x: x.get("date_time", ""))
    return events


async def get_events_for_user_subscriptions(
    user_id: int, period: str = "week"
) -> List[Dict]:
    """Возвращает активные события, которые совпадают с подписками пользователя."""
    subscriptions = await get_user_category_subscriptions(user_id)
    if not subscriptions:
        return []

    period_days = _period_to_days(period)
    result = await _run_query(
        """
        SELECT * FROM events
        WHERE status = 'active'
        ORDER BY date_time
        """,
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    subscriptions_set = {
        item.strip().lower() for item in subscriptions if item and item.strip()
    }
    events: List[Dict] = []

    for row in result[0].rows:
        event_dict = _normalize_row(row)
        event_category = str(event_dict.get("category") or "").strip().lower()
        if event_category not in subscriptions_set:
            continue
        if _event_matches_period_filter(event_dict, now, max_dt):
            events.append(event_dict)

    event_ids = {int(event["id"]) for event in events}
    if event_ids:
        counts_result = await _run_query(
            """
            SELECT event_id, status FROM participants
            """,
        )
        counts: dict[int, dict[str, int]] = {event_id: {"going": 0, "waitlist": 0} for event_id in event_ids}
        for row in counts_result[0].rows:
            if not hasattr(row, "event_id"):
                continue
            event_id = int(row.event_id)
            if event_id not in counts:
                continue
            status = str(row.status)
            if status in {"going", "driver", "passenger"}:
                counts[event_id]["going"] += 1
            elif status == "waitlist":
                counts[event_id]["waitlist"] += 1
        for event in events:
            event_counts = counts.get(int(event["id"]), {})
            event["going_count"] = event_counts.get("going", 0)
            event["waitlist_count"] = event_counts.get("waitlist", 0)

    events.sort(key=lambda x: x.get("date_time", ""))
    return events
