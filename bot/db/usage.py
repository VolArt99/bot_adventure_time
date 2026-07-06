"""Command usage statistics."""

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz

from bot.config import TIMEZONE
from ._core import _run_query

logger = logging.getLogger(__name__)
_USAGE_TZ = pytz.timezone(TIMEZONE)


def usage_date_key(when: datetime | None = None) -> str:
    """Ключ календарного дня для дневных лимитов (в часовом поясе бота)."""
    moment = when or datetime.now(_USAGE_TZ)
    if moment.tzinfo is None:
        moment = _USAGE_TZ.localize(moment)
    else:
        moment = moment.astimezone(_USAGE_TZ)
    return moment.date().isoformat()


async def record_command_usage(role: str, command: str, usage_date: str | None = None) -> None:
    day = usage_date or usage_date_key()
    try:
        prev = await _run_query(
            """
            SELECT usage_count
            FROM command_usage_daily
            WHERE usage_date = $usage_date AND role = $role AND command = $command
            """,
            parameters={"usage_date": day, "role": role, "command": command},
        )
        current = int(prev[0].rows[0].usage_count) if prev and prev[0].rows else 0
        await _run_query(
            """
            INSERT INTO command_usage_daily (usage_date, role, command, usage_count)
            VALUES ($usage_date, $role, $command, $usage_count)
            ON CONFLICT (usage_date, role, command) DO UPDATE SET usage_count = EXCLUDED.usage_count
            """,
            parameters={"usage_date": day, "role": role, "command": command, "usage_count": current + 1},
        )
    except Exception as exc:
        if False:
            logger.warning("Skip command usage stats: table command_usage_daily is missing: %s", exc)
            return
        raise


async def get_command_usage_summary(days: int = 7) -> list[dict[str, Any]]:
    cutoff = (datetime.now(_USAGE_TZ).date() - timedelta(days=max(0, days - 1))).isoformat()
    try:
        result = await _run_query(
            """
            SELECT role, SUM(usage_count) AS total_commands, COUNT(DISTINCT usage_date) AS active_days
            FROM command_usage_daily
            WHERE usage_date >= $cutoff
            GROUP BY role
            ORDER BY total_commands DESC
            """,
            parameters={"cutoff": cutoff},
        )
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


async def get_user_daily_command_count(user_id: int, usage_date: str | None = None) -> int:
    day = usage_date or usage_date_key()
    result = await _run_query(
        """
        SELECT usage_count
        FROM user_command_usage_daily
        WHERE user_id = $user_id AND usage_date = $usage_date
        """,
        parameters={"user_id": int(user_id), "usage_date": day},
    )
    if result and result[0].rows:
        return int(result[0].rows[0].usage_count)
    return 0


async def increment_user_daily_command_count(user_id: int, usage_date: str | None = None) -> None:
    day = usage_date or usage_date_key()
    current = await get_user_daily_command_count(user_id, day)
    await _run_query(
        """
        INSERT INTO user_command_usage_daily (user_id, usage_date, usage_count)
        VALUES ($user_id, $usage_date, $usage_count)
        ON CONFLICT (user_id, usage_date) DO UPDATE SET usage_count = EXCLUDED.usage_count
        """,
        parameters={"user_id": int(user_id), "usage_date": day, "usage_count": current + 1},
    )


async def reset_user_daily_command_count(user_id: int, usage_date: str | None = None) -> int:
    """Сбрасывает дневной счётчик команд пользователя. Возвращает прежнее значение."""
    day = usage_date or usage_date_key()
    previous = await get_user_daily_command_count(user_id, day)
    if previous == 0:
        return 0
    await _run_query(
        """
        DELETE FROM user_command_usage_daily
        WHERE user_id = $user_id AND usage_date = $usage_date
        """,
        parameters={"user_id": int(user_id), "usage_date": day},
    )
    return previous
