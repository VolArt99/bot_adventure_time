"""Birthday commands for approved members."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database import (
    clear_user_birth_date,
    ensure_user_row,
    format_birthday_display,
    get_user_birth_date,
    parse_birthday_input,
    set_user_birth_date,
)
from bot.utils.design import brand_voice

router = Router(name=__name__)


@router.message(Command("birthday"))
async def cmd_birthday(message: Message):
    """Показывает сохранённую дату рождения."""
    user_id = message.from_user.id
    await ensure_user_row(user_id, message.from_user.username)
    stored = await get_user_birth_date(user_id)
    if not stored:
        await message.answer(
            "🎂 День рождения ещё не указан.\n"
            "Добавьте: <code>/set_birthday ДД.ММ</code> (год не нужен).\n"
            "Удалить: /clear_birthday",
            parse_mode="HTML",
        )
        return
    display = format_birthday_display(stored)
    await message.answer(
        f"🎂 Ваш день рождения: <b>{display}</b>\n"
        f"{brand_voice('birthday_saved_hint')}",
        parse_mode="HTML",
    )


@router.message(Command("set_birthday"))
async def cmd_set_birthday(message: Message):
    """Сохраняет день рождения (ДД.ММ, без года)."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "🎂 Укажите дату: <code>/set_birthday ДД.ММ</code>\n"
            "Пример: <code>/set_birthday 15.07</code>",
            parse_mode="HTML",
        )
        return

    mm_dd = parse_birthday_input(parts[1])
    if not mm_dd:
        await message.answer(
            "❌ Не понял дату. Формат: <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code> "
            "(год сохраняться не будет).",
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id
    await ensure_user_row(user_id, message.from_user.username)
    await set_user_birth_date(user_id, mm_dd)
    display = format_birthday_display(mm_dd)
    await message.answer(
        f"✅ Сохранено: <b>{display}</b>\n{brand_voice('birthday_saved_hint')}",
        parse_mode="HTML",
    )


@router.message(Command("clear_birthday"))
async def cmd_clear_birthday(message: Message):
    """Удаляет сохранённую дату рождения."""
    user_id = message.from_user.id
    await ensure_user_row(user_id, message.from_user.username)
    await clear_user_birth_date(user_id)
    await message.answer("🗑 День рождения удалён из профиля.")
