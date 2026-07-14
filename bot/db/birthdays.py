"""Birthday storage and queries (MM-DD, approved members only)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from ._core import _normalize_row, _run_execute, _run_query

_BIRTHDAY_INPUT_RE = re.compile(
    r"^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?$"
)


def parse_birthday_input(raw: str) -> str | None:
    """Parses DD.MM[/YYYY] into canonical MM-DD storage format."""
    text = (raw or "").strip()
    if not text:
        return None
    match = _BIRTHDAY_INPUT_RE.match(text)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= 31:
        return None
    # Validate day for month (ignore leap years — Feb 29 allowed in storage)
    month_days = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if day > month_days[month - 1]:
        return None
    return f"{month:02d}-{day:02d}"


def format_birthday_display(mm_dd: str | None) -> str | None:
    """MM-DD → DD.MM for user-facing text."""
    if not mm_dd or "-" not in mm_dd:
        return None
    month, day = mm_dd.split("-", 1)
    if len(month) != 2 or len(day) != 2:
        return None
    return f"{day}.{month}"


async def set_user_birth_date(user_id: int, mm_dd: str) -> bool:
    await _run_execute(
        """
        UPDATE users SET birth_date = $birth_date WHERE id = $user_id
        """,
        parameters={"user_id": int(user_id), "birth_date": mm_dd},
    )
    return True


async def clear_user_birth_date(user_id: int) -> bool:
    await _run_execute(
        """
        UPDATE users SET birth_date = NULL WHERE id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    return True


async def get_user_birth_date(user_id: int) -> str | None:
    result = await _run_query(
        """
        SELECT birth_date FROM users WHERE id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    if not result[0].rows:
        return None
    value = result[0].rows[0].birth_date
    return str(value) if value else None


async def ensure_user_row(user_id: int, username: str | None = None) -> None:
    await _run_execute(
        """
        INSERT INTO users (id, username) VALUES ($user_id, $username)
        ON CONFLICT (id) DO UPDATE SET username = COALESCE(EXCLUDED.username, users.username)
        """,
        parameters={"user_id": int(user_id), "username": username or ""},
    )


async def get_approved_members_with_birthday_on(mm_dd: str) -> list[dict[str, Any]]:
    """Returns approved members whose birthday matches MM-DD."""
    result = await _run_query(
        """
        SELECT u.id AS user_id, u.username, am.full_name
        FROM users AS u
        INNER JOIN approved_members AS am ON am.user_id = u.id
        WHERE u.birth_date = $mm_dd
        ORDER BY am.full_name NULLS LAST, u.username NULLS LAST, u.id
        """,
        parameters={"mm_dd": mm_dd},
    )
    return [_normalize_row(row) for row in result[0].rows]


async def was_birthday_greeted(user_id: int, greeted_on: date) -> bool:
    result = await _run_query(
        """
        SELECT 1 FROM birthday_greetings_log
        WHERE user_id = $user_id AND greeted_on = $greeted_on
        LIMIT 1
        """,
        parameters={"user_id": int(user_id), "greeted_on": greeted_on},
    )
    return bool(result[0].rows)


async def record_birthday_greeting(user_id: int, greeted_on: date) -> None:
    await _run_execute(
        """
        INSERT INTO birthday_greetings_log (user_id, greeted_on, created_at)
        VALUES ($user_id, $greeted_on, $created_at)
        ON CONFLICT (user_id, greeted_on) DO NOTHING
        """,
        parameters={
            "user_id": int(user_id),
            "greeted_on": greeted_on,
            "created_at": datetime.now(timezone.utc),
        },
    )
