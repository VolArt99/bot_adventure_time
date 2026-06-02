from __future__ import annotations

from bot.config import ADMIN_IDS, OWNER_ID


def is_owner(user_id: int | None) -> bool:
    """Возвращает True для владельца бота из OWNER_ID."""
    return bool(user_id is not None and OWNER_ID > 0 and int(user_id) == OWNER_ID)


def is_admin(user_id: int | None) -> bool:
    """Возвращает True для пользователя из ADMIN_IDS."""
    return bool(user_id is not None and int(user_id) in ADMIN_IDS)


def is_admin_or_owner(user_id: int | None) -> bool:
    """Единая проверка расширенных прав: админ или владелец."""
    return is_admin(user_id) or is_owner(user_id)
