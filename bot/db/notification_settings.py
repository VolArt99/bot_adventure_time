"""User notification mode preferences."""

from __future__ import annotations

from .users import get_or_create_user
from ._core import _run_query

VALID_MODES = frozenset({"all", "mine", "off"})

MODE_LABELS = {
    "all": "🔔 Все уведомления",
    "mine": "📍 Только мои",
    "off": "🔕 Отключены",
}


async def get_user_notification_settings(user_id: int) -> str:
    """Возвращает режим уведомлений: all, mine или off."""
    await get_or_create_user(user_id)
    result = await _run_query(
        """
        SELECT notification_settings
        FROM users
        WHERE id = $user_id
        """,
        parameters={"user_id": int(user_id)},
    )
    if not result[0].rows:
        return "all"
    mode = str(result[0].rows[0].notification_settings or "all").strip().lower()
    return mode if mode in VALID_MODES else "all"


async def set_user_notification_settings(user_id: int, mode: str) -> None:
    normalized = str(mode or "").strip().lower()
    if normalized not in VALID_MODES:
        raise ValueError(f"Invalid notification mode: {mode}")
    await get_or_create_user(user_id)
    await _run_query(
        """
        UPDATE users
        SET notification_settings = $mode
        WHERE id = $user_id
        """,
        parameters={"user_id": int(user_id), "mode": normalized},
    )


def should_deliver_notification(mode: str, *, kind: str) -> bool:
    """kind: broadcast — подписки; personal — явка, резерв, чеки."""
    if mode == "off":
        return False
    if mode == "mine":
        return kind == "personal"
    return True
