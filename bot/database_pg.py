"""PostgreSQL database layer for Bot Adventure Time."""

import logging
import json
import time
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from bot.db_pool import execute, fetch

logger = logging.getLogger(__name__)


class _CompatRow:
    def __init__(self, record):
        self._record = record

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._record[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _CompatResultSet:
    def __init__(self, records):
        self.rows = [
            record if isinstance(record, _CompatRow) else _CompatRow(record)
            for record in records
        ]


async def _run_query(query: str, parameters: dict | None = None):
    records = await fetch(query, parameters)
    return [_CompatResultSet(records)]


async def _run_execute(query: str, parameters: dict | None = None) -> None:
    await execute(query, parameters)


async def init_db():
    """Creates tables on first startup."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            notification_settings TEXT DEFAULT 'all',
            stats_count BIGINT DEFAULT 0,
            birth_date TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id BIGINT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            date_time TEXT NOT NULL,
            duration_minutes BIGINT,
            period_end TEXT,
            location TEXT,
            price_total DOUBLE PRECISION,
            price_per_person DOUBLE PRECISION,
            participant_limit BIGINT,
            thread_id BIGINT,
            message_id BIGINT,
            creator_id BIGINT,
            responsible_id BIGINT,
            weather_info TEXT,
            carpool_enabled BOOLEAN DEFAULT false,
            status TEXT DEFAULT 'active',
            category TEXT,
            created_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS participants (
            id BIGINT PRIMARY KEY,
            event_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            status TEXT,
            car_seats BIGINT,
            passenger_of BIGINT,
            joined_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reminder_jobs (
            id BIGINT PRIMARY KEY,
            event_id BIGINT NOT NULL,
            interval_seconds BIGINT,
            scheduled_time TIMESTAMPTZ,
            sent BOOLEAN DEFAULT false
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forum_topics (
            id BIGINT PRIMARY KEY,
            message_thread_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            is_closed BOOLEAN DEFAULT false,
            is_hidden BOOLEAN DEFAULT false,
            discovered_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_category_subscriptions (
            user_id BIGINT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, category)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS random_meeting_opt_in (
            user_id BIGINT PRIMARY KEY,
            is_enabled BOOLEAN NOT NULL,
            updated_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pending_users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            status TEXT,
            created_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fsm_states (
            bot_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            thread_id BIGINT NOT NULL DEFAULT 0,
            business_connection_id TEXT NOT NULL DEFAULT '',
            destiny TEXT NOT NULL,
            state TEXT,
            data_json TEXT,
            updated_at TIMESTAMPTZ,
            PRIMARY KEY (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS approved_members (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            join_date TIMESTAMPTZ,
            intro_status TEXT DEFAULT 'pending'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS command_usage_daily (
            usage_date TEXT NOT NULL,
            role TEXT NOT NULL,
            command TEXT NOT NULL,
            usage_count BIGINT NOT NULL,
            PRIMARY KEY (usage_date, role, command)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_events (
            id BIGINT PRIMARY KEY,
            group_id BIGINT NOT NULL,
            organizer_id BIGINT NOT NULL,
            title TEXT,
            total_amount DOUBLE PRECISION NOT NULL,
            transfer_target_type TEXT,
            transfer_target_value TEXT,
            transfer_bank TEXT,
            transfer_bank_custom TEXT,
            transfer_recipient_name TEXT,
            status TEXT NOT NULL,
            source_event_id BIGINT,
            thread_id BIGINT,
            message_id BIGINT,
            created_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_participants (
            split_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            is_paid BOOLEAN NOT NULL,
            share_amount DOUBLE PRECISION NOT NULL,
            joined_at TIMESTAMPTZ,
            PRIMARY KEY (split_id, user_id)
        )
        """,
    ]

    for statement in statements:
        await execute(statement.strip())

    for column_def in ("responsible_id BIGINT", "period_end TEXT"):
        column_name = column_def.split()[0]
        try:
            await execute(f"ALTER TABLE events ADD COLUMN IF NOT EXISTS {column_def}")
            logger.info("Ensured column events.%s", column_name)
        except Exception as exc:
            logger.warning("Could not alter events.%s: %s", column_name, exc)

    for column_def in (
        "title TEXT",
        "transfer_target_type TEXT",
        "transfer_target_value TEXT",
        "transfer_bank TEXT",
        "transfer_bank_custom TEXT",
        "transfer_recipient_name TEXT",
        "thread_id BIGINT",
        "message_id BIGINT",
    ):
        column_name = column_def.split()[0]
        try:
            await execute(f"ALTER TABLE split_bill_events ADD COLUMN IF NOT EXISTS {column_def}")
            logger.info("Ensured column split_bill_events.%s", column_name)
        except Exception as exc:
            logger.warning("Could not alter split_bill_events.%s: %s", column_name, exc)

    logger.info("PostgreSQL tables created or already exist")


async def get_or_create_user(user_id: int, username: str = None) -> int:
    """Возвращает пользователя из БД, создаёт если нет."""
    # Проверяем, существует ли пользователь
    result = await _run_query(
            """
            SELECT id FROM users WHERE id = $user_id
            """,
            parameters={
                "user_id": user_id,
            })

    if not result[0].rows:
        # Создаем нового пользователя
        await _run_query(
                """
                INSERT INTO users (id, username) VALUES ($user_id, $username)
                """,
                parameters={
                    "user_id": user_id,
                    "username": username or "",
                })

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
            })


async def get_pending_user(user_id: int) -> Optional[Dict[str, Any]]:
    result = await _run_query(
            """
            SELECT user_id, username, full_name, status, created_at
            FROM pending_users
            WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)})
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def delete_pending_user(user_id: int) -> None:
    await _run_query(
            """
            DELETE FROM pending_users WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)})


async def is_member_approved(user_id: int) -> bool:
    result = await _run_query(
            """
            SELECT user_id FROM approved_members WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)})
    return bool(result[0].rows)


async def get_approved_member(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает запись одобренного участника или None."""
    result = await _run_query(
            """
            SELECT user_id, username, full_name, join_date, intro_status
            FROM approved_members
            WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)})
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
            })
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
            })


async def delete_approved_member(user_id: int) -> None:
    await _run_query(
            """
            DELETE FROM approved_members
            WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)})


async def record_command_usage(role: str, command: str, usage_date: str | None = None) -> None:
    day = usage_date or datetime.utcnow().date().isoformat()
    try:
        prev = await _run_query(
                """
                SELECT usage_count
                FROM command_usage_daily
                WHERE usage_date = $usage_date AND role = $role AND command = $command
                """,
                parameters={"usage_date": day, "role": role, "command": command})
        current = int(prev[0].rows[0].usage_count) if prev and prev[0].rows else 0
        await _run_query(
                """
                INSERT INTO command_usage_daily (usage_date, role, command, usage_count)
                VALUES ($usage_date, $role, $command, $usage_count)
                ON CONFLICT (usage_date, role, command) DO UPDATE SET usage_count = EXCLUDED.usage_count
                """,
                parameters={"usage_date": day, "role": role, "command": command, "usage_count": current + 1})
    except Exception as exc:
        if False:
            logger.warning("Skip command usage stats: table command_usage_daily is missing: %s", exc)
            return
        raise


async def get_command_usage_summary(days: int = 7) -> list[dict[str, Any]]:
    cutoff = (datetime.utcnow().date() - timedelta(days=max(0, days - 1))).isoformat()
    try:
        result = await _run_query(
                """
                SELECT role, SUM(usage_count) AS total_commands, COUNT(DISTINCT usage_date) AS active_days
                FROM command_usage_daily
                WHERE usage_date >= $cutoff
                GROUP BY role
                ORDER BY total_commands DESC
                """,
                parameters={"cutoff": cutoff})
    except Exception as exc:
        if False:
            logger.warning("Cannot build command usage summary: table command_usage_daily is missing: %s", exc)
            return []
        raise
    items: list[dict[str, Any]] = []
    for row in result[0].rows if result else []:
        total = int(row.total_commands or 0)
        active_days = max(1, int(row.active_days or 1))
        items.append(
            {
                "role": str(row.role),
                "total_commands": total,
                "active_days": active_days,
                "avg_per_day": round(total / active_days, 2),
            }
        )
    return items


async def get_pending_intro_members() -> list[Dict[str, Any]]:
    result = await _run_query(
            """
            SELECT user_id, username, full_name, join_date, intro_status
            FROM approved_members
            WHERE intro_status = 'pending'
            ORDER BY join_date
            """)
    return [_normalize_row(row) for row in result[0].rows]


async def get_intro_members_statuses() -> list[Dict[str, Any]]:
    result = await _run_query(
            """
            SELECT user_id, username, full_name, join_date, intro_status
            FROM approved_members
            ORDER BY join_date
            """)
    return [_normalize_row(row) for row in result[0].rows]


async def get_approved_member_ids() -> list[int]:
    result = await _run_query(
            """
            SELECT user_id
            FROM approved_members
            """)
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
            })


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
            """)

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


async def create_event(event_data: Dict[str, Any]) -> int:
    """Создаёт мероприятие и возвращает его ID."""
    # Генерируем ID для мероприятия
    import time

    event_id = int(time.time() * 1000)  # Используем timestamp в миллисекундах

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
            })

    return event_id


async def get_event(event_id: int) -> Optional[Dict]:
    """Возвращает мероприятие по ID."""
    result = await _run_query(
            """
            SELECT * FROM events WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
            })

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
            })


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
            """)

    return [_normalize_row(row) for row in result[0].rows]


def _normalize_row(row) -> Dict[str, Any]:
    """Convert a DB row to a plain Python dict."""
    while hasattr(row, "_record") and not isinstance(row, dict):
        row = row._record
    if isinstance(row, dict):
        row_items = row.items()
    elif hasattr(row, "items") and callable(row.items):
        row_items = row.items()
    else:
        row_items = ((column, row[column]) for column in row.keys())

    event_dict: Dict[str, Any] = {}
    for column, value in row_items:
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        event_dict[column] = value
    return event_dict


def _period_to_days(period: str, default_days: int = 7) -> int:
    return {
        "week": 7,
        "month": 30,
        "all": 365 * 10,
    }.get(period, default_days)


def _parse_event_datetime(value: Any) -> Optional[datetime]:
    """Пытается распарсить дату события из строки/объекта datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _event_matches_period_filter(
    event_dict: Dict, now: datetime, max_dt: datetime
) -> bool:
    """Проверяет, попадает ли активное мероприятие в выбранный период дайджеста/афиши."""
    event_dt = _parse_event_datetime(event_dict.get("date_time"))
    if event_dt is None:
        return False
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)

    period_end_dt = _parse_event_datetime(event_dict.get("period_end"))
    if period_end_dt and period_end_dt.tzinfo is None:
        period_end_dt = period_end_dt.replace(tzinfo=timezone.utc)

    if period_end_dt and period_end_dt > event_dt:
        if period_end_dt < now:
            return False
        if event_dt <= now:
            return True
        return event_dt <= max_dt

    return now <= event_dt <= max_dt


async def add_participant(
    event_id: int,
    user_id: int,
    status: str = "going",
    car_seats: int = None,
    passenger_of: int = None,
) -> bool:
    """Добавляет участника в событие."""
    # Проверяем, не существует ли уже участник
    result = await _run_query(
            """
            SELECT id FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            })

    if result[0].rows:
        return False

    # Генерируем ID для участника
    import time

    participant_id = int(time.time() * 1000) + user_id  # Уникальный ID

    await _run_query(
            """
            INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, $status, $car_seats, $passenger_of)
            """,
            parameters={
                "id": participant_id,
                "event_id": event_id,
                "user_id": user_id,
                "status": status,
                "car_seats": car_seats or 0,
                "passenger_of": passenger_of or 0,
            })

    return True


async def remove_participant(event_id: int, user_id: int):
    """Удаляет участника из события (и пассажиров если водитель)."""
    # Получаем статус участника
    result = await _run_query(
            """
            SELECT status FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            })

    if result[0].rows:
        status = result[0].rows[0].status
        if status == "driver":
            # Удаляем всех пассажиров этого водителя
            await _run_query(
                    """
                    DELETE FROM participants 
                    WHERE event_id = $event_id AND passenger_of = $driver_id
                    """,
                    parameters={
                        "event_id": event_id,
                        "driver_id": user_id,
                    })

    # Удаляем самого участника
    await _run_query(
            """
            DELETE FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            })


async def get_participants(event_id: int, status: str = None) -> List[int]:
    """Возвращает список ID участников с указанным статусом."""
    if status:
        query = """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id AND status = $status
        """
        params = {
            "event_id": event_id,
            "status": status,
        }
    else:
        query = """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id
        """
        params = {
            "event_id": event_id,
        }

    result = await _run_query(
            query,
            parameters=params)

    return [row.user_id for row in result[0].rows]


async def get_main_participants(event_id: int) -> List[int]:
    """Возвращает ID участников основного состава (идут + карпулинг)."""
    result = await _run_query(
            """
            SELECT DISTINCT user_id FROM participants 
            WHERE event_id = $event_id AND status IN ('going', 'driver', 'passenger')
            """,
            parameters={
                "event_id": event_id,
            })

    return [row.user_id for row in result[0].rows]


async def cancel_event(event_id: int) -> None:
    """Помечает мероприятие как отменённое и очищает участников."""
    # Помечаем мероприятие как отменённое
    await _run_query(
            """
            UPDATE events SET status = 'cancelled' WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
            })

    # Удаляем всех участников
    await _run_query(
            """
            DELETE FROM participants WHERE event_id = $event_id
            """,
            parameters={
                "event_id": event_id,
            })


async def get_user_stats(user_id: int) -> Dict:
    """⚠️ НОВОЕ: Возвращает статистику пользователя."""
    # Получаем количество мероприятий, где пользователь был организатором
    result_creator = await _run_query(
            """
            SELECT COUNT(*) as events_count FROM events 
            WHERE creator_id = $user_id AND status = 'active'
            """,
            parameters={
                "user_id": user_id,
            })

    events_count = (
        result_creator[0].rows[0].events_count if result_creator[0].rows else 0
    )

    # Получаем общее количество участий
    result_participations = await _run_query(
            """
            SELECT COUNT(DISTINCT event_id) as total_participations FROM participants 
            WHERE user_id = $user_id
            """,
            parameters={
                "user_id": user_id,
            })

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
            """)
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
            """)
    attendance_count = (
        int(attendance_result[0].rows[0].attendance_count)
        if attendance_result and attendance_result[0].rows
        else 0
    )
    avg_attendance = round(attendance_count / active_events, 2) if active_events else 0.0

    no_show_result = await _run_query(
            """
            SELECT COUNT(*) AS no_show
            FROM participants
            WHERE status = 'no_show'
            """)
    no_show = (
        int(no_show_result[0].rows[0].no_show)
        if no_show_result and no_show_result[0].rows
        else 0
    )

    top_categories_result = await _run_query(
            """
            SELECT category, COUNT(*) AS cnt
            FROM events
            WHERE status = 'active'
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 5
            """)

    top_categories: List[Dict[str, Any]] = []
    for row in top_categories_result[0].rows if top_categories_result else []:
        category_name = (row.category or 'Без категории').strip() if isinstance(row.category, str) else 'Без категории'
        top_categories.append({'category': category_name, 'cnt': int(row.cnt)})

    return {
        'active_events': active_events,
        'avg_attendance': avg_attendance,
        'no_show': no_show,
        'top_categories': top_categories,
    }


async def get_top_participants(days: int = 30, limit: int = 3) -> List[Dict]:
    """Топ участников по количеству участий за период."""
    safe_days = max(0, int(days))
    cutoff_ts = datetime.utcnow() - timedelta(days=safe_days)

    # Получаем топ участников за последние N дней
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
            })

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


async def create_split_bill(
    *,
    group_id: int,
    organizer_id: int,
    title: str | None,
    total_amount: float,
    transfer_target_type: str | None = None,
    transfer_target_value: str | None = None,
    transfer_bank: str | None = None,
    transfer_bank_custom: str | None = None,
    transfer_recipient_name: str | None = None,
    source_event_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    result = await _run_query(
            """
            SELECT COALESCE(MAX(id), 0) + 1 AS new_id FROM split_bill_events
            """)
    split_id = int(result[0].rows[0].new_id)

    await _run_query(
            """
            INSERT INTO split_bill_events
            (id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, created_at)
            VALUES ($id, $group_id, $organizer_id, $title, $total_amount, $transfer_target_type, $transfer_target_value, $transfer_bank, $transfer_bank_custom, $transfer_recipient_name, $status, $source_event_id, $created_at)
            ON CONFLICT (id) DO NOTHING
            """,
            parameters={
                "id": split_id,
                "group_id": int(group_id),
                "organizer_id": int(organizer_id),
                "title": (title or "").strip() or None,
                "total_amount": float(total_amount),
                "transfer_target_type": transfer_target_type,
                "transfer_target_value": transfer_target_value,
                "transfer_bank": transfer_bank,
                "transfer_bank_custom": transfer_bank_custom,
                "transfer_recipient_name": transfer_recipient_name,
                "status": "open",
                "source_event_id": source_event_id,
                "created_at": now,
            })
    return split_id


async def get_split_bill(split_id: int) -> Optional[dict[str, Any]]:
    result = await _run_query(
            """
            SELECT id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, thread_id, message_id, created_at, closed_at
            FROM split_bill_events
            WHERE id = $split_id
            """,
            parameters={"split_id": int(split_id)})
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def update_split_bill_message_id(split_id: int, thread_id: int | None, message_id: int) -> None:
    """Сохраняет id опубликованной split-bill карточки для последующих refresh-обновлений."""
    await _run_query(
            """
            UPDATE split_bill_events
            SET thread_id = $thread_id, message_id = $message_id
            WHERE id = $split_id
            """,
            parameters={
                "split_id": int(split_id),
                "thread_id": int(thread_id) if thread_id is not None else None,
                "message_id": int(message_id),
            })


async def get_event_participant_ids(event_id: int) -> list[int]:
    result = await _run_query(
            """
            SELECT DISTINCT user_id FROM participants WHERE event_id = $event_id
            """,
            parameters={"event_id": int(event_id)})
    return [int(row.user_id) for row in result[0].rows]


async def get_split_bill_participants(split_id: int) -> list[dict[str, Any]]:
    result = await _run_query(
            """
            SELECT user_id, is_paid, share_amount, joined_at
            FROM split_bill_participants
            WHERE split_id = $split_id
            ORDER BY joined_at
            """,
            parameters={"split_id": int(split_id)})
    return [_normalize_row(row) for row in result[0].rows]


async def recalculate_split_bill_shares(split_id: int) -> None:
    bill = await get_split_bill(split_id)
    if not bill:
        return
    participants = await get_split_bill_participants(split_id)
    if not participants:
        return
    share = round(float(bill["total_amount"]) / len(participants), 2)
    for participant in participants:
        await _run_execute(
            """
            UPDATE split_bill_participants
            SET share_amount = $share_amount
            WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={
                "split_id": int(split_id),
                "user_id": int(participant["user_id"]),
                "share_amount": share,
            },
        )


async def add_split_bill_participant(split_id: int, user_id: int) -> None:
    await _run_query(
            """
            INSERT INTO split_bill_participants (split_id, user_id, is_paid, share_amount, joined_at)
            VALUES ($split_id, $user_id, false, 0.0, $joined_at)
            ON CONFLICT (split_id, user_id) DO UPDATE SET is_paid = EXCLUDED.is_paid, share_amount = EXCLUDED.share_amount, joined_at = EXCLUDED.joined_at
            """,
            parameters={
                "split_id": int(split_id),
                "user_id": int(user_id),
                "joined_at": datetime.utcnow(),
            })
    await recalculate_split_bill_shares(split_id)


async def remove_split_bill_participant(split_id: int, user_id: int) -> None:
    await _run_query(
            """
            DELETE FROM split_bill_participants WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={"split_id": int(split_id), "user_id": int(user_id)})
    await recalculate_split_bill_shares(split_id)


async def mark_split_bill_paid(split_id: int, user_id: int) -> None:
    await _run_query(
            """
            UPDATE split_bill_participants
            SET is_paid = true
            WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={"split_id": int(split_id), "user_id": int(user_id)})


async def close_split_bill(split_id: int) -> None:
    await _run_query(
            """
            UPDATE split_bill_events
            SET status = 'closed', closed_at = $closed_at
            WHERE id = $split_id
            """,
            parameters={"split_id": int(split_id), "closed_at": datetime.utcnow()})

    
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
            })

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
        # Мероприятия, где пользователь организатор
        query = """
            SELECT e.* FROM events e
            WHERE e.creator_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    elif status == "participant":
        # Мероприятия, где пользователь участник
        query = """
            SELECT DISTINCT e.* FROM events e
            JOIN participants p ON e.id = p.event_id
            WHERE p.user_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    else:
        # Все мероприятия пользователя (и как организатор, и как участник)
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
            parameters=params)

    return [_normalize_row(row) for row in result[0].rows]


async def move_from_waitlist(event_id: int) -> Optional[int]:
    """Перемещает первого из резерва в основной список."""
    event = await get_event(event_id)
    if not event:
        return None

    participant_limit = event.get("participant_limit") or 0
    if participant_limit > 0:
        going = await get_main_participants(event_id)
        if len(going) >= participant_limit:
            return None
        
    # Получаем первого участника из резерва
    result = await _run_query(
            """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id AND status = 'waitlist'
            ORDER BY joined_at
            LIMIT 1
            """,
            parameters={
                "event_id": event_id,
            })

    if not result[0].rows:
        return None

    user_id = result[0].rows[0].user_id

    # Обновляем статус на 'going'
    await _run_query(
            """
            UPDATE participants 
            SET status = 'going' 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            })

    return user_id


async def get_drivers_with_passengers(event_id: int) -> List[Dict]:
    """Возвращает список водителей с их пассажирами."""
    # Получаем всех водителей
    result_drivers = await _run_query(
            """
            SELECT user_id, car_seats FROM participants 
            WHERE event_id = $event_id AND status = 'driver'
            """,
            parameters={
                "event_id": event_id,
            })

    drivers = []
    for row in result_drivers[0].rows:
        driver_id = row.user_id
        car_seats = row.car_seats

        # Получаем пассажиров этого водителя
        result_passengers = await _run_query(
                """
                SELECT user_id FROM participants 
                WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
                """,
                parameters={
                    "event_id": event_id,
                    "driver_id": driver_id,
                })

        passengers = [
            row_passenger.user_id for row_passenger in result_passengers[0].rows
        ]

        drivers.append(
            {
                "user_id": driver_id,
                "car_seats": car_seats,
                "passengers": passengers,
            }
        )

    return drivers


async def get_driver_free_seats(driver_id: int, event_id: int) -> int:
    """Возвращает количество свободных мест у водителя."""
    # Получаем информацию о водителе
    result_driver = await _run_query(
            """
            SELECT car_seats FROM participants 
            WHERE event_id = $event_id AND user_id = $driver_id AND status = 'driver'
            """,
            parameters={
                "event_id": event_id,
                "driver_id": driver_id,
            })

    if not result_driver[0].rows:
        return 0

    car_seats = result_driver[0].rows[0].car_seats

    # Получаем количество пассажиров
    result_passengers = await _run_query(
            """
            SELECT COUNT(*) as passenger_count FROM participants 
            WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
            """,
            parameters={
                "event_id": event_id,
                "driver_id": driver_id,
            })

    passenger_count = (
        result_passengers[0].rows[0].passenger_count if result_passengers[0].rows else 0
    )

    # Свободные места = общие места - пассажиры - 1 (сам водитель)
    free_seats = car_seats - passenger_count - 1
    return max(0, free_seats)


async def set_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Атомарно назначает пользователя водителем, обновляя существующую запись участника."""
    participant_id = int(time.time() * 1000) + int(user_id)

    await _run_execute(
        """
        DELETE FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
        },
    )
    await _run_execute(
        """
        INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
        VALUES ($id, $event_id, $user_id, 'driver', $car_seats, 0)
        """,
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "car_seats": int(car_seats),
        },
    )
    return True


async def set_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Атомарно назначает пользователя пассажиром выбранного водителя."""
    free_seats = await get_driver_free_seats(driver_id, event_id)
    if free_seats <= 0:
        return False
    participant_id = int(time.time() * 1000) + int(user_id)
    await _run_execute(
        """
        DELETE FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
        },
    )
    await _run_execute(
        """
        INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
        VALUES ($id, $event_id, $user_id, 'passenger', 0, $driver_id)
        """,
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "driver_id": int(driver_id),
        },
    )
    return True


async def add_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Добавляет или обновляет водителя."""
    return await set_driver(event_id, user_id, car_seats)

async def add_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Добавляет или обновляет пассажира к водителю."""
    return await set_passenger(event_id, user_id, driver_id)


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
            })
    return True


async def get_all_topics() -> List[Dict]:
    result = await _run_query(
            """
            SELECT message_thread_id, name, is_closed, is_hidden
            FROM forum_topics
            ORDER BY message_thread_id
            """)
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
            parameters={"message_thread_id": int(message_thread_id)})
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


async def sync_topics_from_config() -> int:
    import asyncio

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


async def set_random_meeting_opt_in(user_id: int, is_enabled: bool) -> None:
    await _run_query(
            """
            INSERT INTO random_meeting_opt_in (user_id, is_enabled, updated_at)
            VALUES ($user_id, $is_enabled, NOW())
            ON CONFLICT (user_id) DO UPDATE SET is_enabled = EXCLUDED.is_enabled, updated_at = NOW()
            """,
            parameters={"user_id": int(user_id), "is_enabled": bool(is_enabled)})


async def get_random_meeting_opt_in_users() -> list[int]:
    result = await _run_query(
            """
            SELECT r.user_id AS user_id
            FROM random_meeting_opt_in AS r
            INNER JOIN approved_members AS am ON am.user_id = r.user_id
            WHERE r.is_enabled = true
            ORDER BY r.user_id
            """)
    return [row.user_id for row in result[0].rows]


async def update_event_status(event_id: int, status: str):
    """Обновляет статус мероприятия."""
    await _run_query(
            """
            UPDATE events SET status = $status WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
                "status": status,
            })


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
            })
    

async def get_events_for_digest(period: str = "week") -> List[Dict]:
    """Получение предстоящих активных мероприятий для дайджеста."""
    period_days = _period_to_days(period)
    result = await _run_query(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            ORDER BY date_time
            """)

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
                """)
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


async def set_user_category_subscriptions(user_id: int, categories: list[str]) -> None:
    """Перезаписывает список подписок пользователя по категориям."""
    # Удаляем существующие подписки пользователя
    await _run_query(
            """
            DELETE FROM user_category_subscriptions WHERE user_id = $user_id
            """,
            parameters={
                "user_id": user_id,
            })

    # Добавляем новые подписки
    for category in categories:
        if category.strip():  # Пропускаем пустые категории
            await _run_query(
                    """
                    INSERT INTO user_category_subscriptions (user_id, category)
                    VALUES ($user_id, $category)
                    """,
                    parameters={
                        "user_id": user_id,
                        "category": category.strip(),
                    })

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
            })

    return [row.category for row in result[0].rows]


async def get_events_for_user_subscriptions(
    user_id: int, period: str = "week"
) -> List[Dict]:
    """Возвращает активные события, которые совпадают с подписками пользователя."""
    # Получаем подписки пользователя
    subscriptions = await get_user_category_subscriptions(user_id)
    if not subscriptions:
        return []

    period_days = _period_to_days(period)
    result = await _run_query(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            ORDER BY date_time
            """)

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
                """)
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
