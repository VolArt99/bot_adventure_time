"""Проверки доступа к командам и подсказкам меню."""

from __future__ import annotations

from bot.commands import COMMANDS_BY_KEY
from bot.config import MEMBER_ALLOWED_COMMANDS, OUTSIDER_ALLOWED_COMMANDS, RESTRICTED_COMMANDS
from bot.utils.roles import is_admin_or_owner


def can_view_command_hint(
    command_key: str,
    user_id: int,
    *,
    is_approved_member: bool,
) -> bool:
    """Возвращает True, если пользователю можно показать подсказку по команде."""
    spec = COMMANDS_BY_KEY.get(command_key)
    if spec is None:
        return False

    if is_admin_or_owner(user_id):
        return True

    command = spec.command
    if command in RESTRICTED_COMMANDS:
        return False

    if spec.group == "admin":
        return False

    if is_approved_member:
        return command in MEMBER_ALLOWED_COMMANDS

    return command in OUTSIDER_ALLOWED_COMMANDS
