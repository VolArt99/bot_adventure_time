from html import escape

from aiogram import Router
from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import GROUP_ID, TIMEZONE
from bot.database import (
    delete_approved_member,
    get_admin_report_metrics,
    get_approved_member_ids,
    get_member_reengage_candidates,
    get_topic_name_by_thread_id,
    get_user_category_subscriptions,
    reset_user_daily_command_count,
    upsert_approved_member,
)
from bot.filters.admin import admin_only
from bot.keyboards import broadcast_topics_keyboard, period_keyboard
from bot.utils.afisha import build_events_broadcast_text
from bot.utils.helpers import get_user_mention, resolve_member_user_id
from bot.utils.ui import ok
from bot.utils.topics import get_topics_list_from_db
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE

router = Router(name=__name__)


@router.message(Command("admin_report"))
@admin_only
async def cmd_admin_report(message: Message):
    metrics = await get_admin_report_metrics()
    top_categories = metrics["top_categories"]
    if top_categories:
        categories_text = "\n".join(
            f"• {escape(str(row['category']))} — {row['cnt']}" for row in top_categories
        )
    else:
        categories_text = "• пока нет данных"

    text = (
        "<b>Админ · отчёт</b>\n\n"
        f"Активные: <b>{metrics['active_events']}</b>\n"
        f"Средняя явка: <b>{metrics['avg_attendance']}</b>\n\n"
        f"<b>Топ категорий</b>\n{categories_text}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("send_events_list"))
@admin_only
async def cmd_send_events_list(message: Message):
    await message.answer(
        "Выберите период для публикации списка мероприятий:",
        reply_markup=period_keyboard("broadcast_period"),
    )


@router.callback_query(F.data.startswith("broadcast_period_"))
@admin_only
async def cb_send_events_list_choose_topic(callback: CallbackQuery):
    period = callback.data.removeprefix("broadcast_period_")
    if period not in {"week", "month", "all"}:
        await finalize_callback(callback, "Некорректный период", show_alert=True)
        return

    topics = await get_topics_list_from_db()
    await callback.message.answer(
        "Выберите группу/подгруппу, куда отправить афишу:",
        reply_markup=broadcast_topics_keyboard(topics, period),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data.startswith("broadcast_topic_"))
@admin_only
async def cb_send_events_list_publish(callback: CallbackQuery):
    _, _, period, thread_raw = callback.data.split("_", 3)
    thread_id = int(thread_raw) if thread_raw != "0" else None

    text = await build_events_broadcast_text(period)
    await callback.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        parse_mode="HTML",
        message_thread_id=thread_id,
        disable_web_page_preview=True,
    )

    topic_name = await get_topic_name_by_thread_id(thread_id)
    target = topic_name or "Основной чат"
    await callback.message.answer(ok(f"Список мероприятий отправлен в: {target}."))
    await finalize_callback(callback, "Отправлено", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(Command("reset_user_limit"))
@admin_only
async def cmd_reset_user_limit(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(
            "Использование: <code>/reset_user_limit &lt;user_id|@username&gt;</code>\n"
            f"Сбрасывает дневной лимит команд участника (сутки по {TIMEZONE}).\n"
            "Пример: <code>/reset_user_limit @ivan</code>",
            parse_mode="HTML",
        )
        return

    user_id = await resolve_member_user_id(parts[1], message.bot)
    if user_id is None:
        await message.answer(
            "❌ Не удалось определить пользователя. Укажите числовой user_id или @username."
        )
        return

    previous = await reset_user_daily_command_count(user_id)
    mention = await get_user_mention(user_id, message.bot)
    await message.answer(
        ok(
            f"Лимит сброшен для {mention} "
            f"(<code>{user_id}</code>, было использовано: {previous})."
        ),
        parse_mode="HTML",
    )


@router.message(Command("member_reengage"))
@admin_only
async def cmd_member_reengage(message: Message):
    threshold_days = 30
    candidates = await get_member_reengage_candidates(days_inactive=threshold_days)
    if not candidates:
        await message.answer("✅ Нет «молчащих» участников: все были активны в последнее время.")
        return

    lines = [
        f"🤝 <b>Re-engage отчёт</b> (не участвовали ≥ {threshold_days} дней):",
        "Ниже — кого можно мягко позвать на релевантные категории.",
    ]
    for member in candidates[:20]:
        user_id = int(member["user_id"])
        mention = await get_user_mention(user_id, message.bot)
        subs = await get_user_category_subscriptions(user_id)
        relevant = ", ".join(sorted(set(subs))[:3]) if subs else "без подписок"
        safe_relevant = escape(relevant)
        invite_hint = (
            f"Привет! Давно не виделись 🙂 Скоро будет активность по категориям: {relevant}. "
            "Будем рады видеть тебя!"
        )
        lines.append(
            f"\n• {mention} — молчит <b>{member['inactive_days']}</b> дн.\n"
            f"  Релевантно: <i>{safe_relevant}</i>\n"
            f"  Пинг-шаблон: <code>{escape(invite_hint)}</code>"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("sync_members"))
@admin_only
async def cmd_sync_members(message: Message):
    if GROUP_ID == 0:
        await message.answer("❌ GROUP_ID не задан. Проверьте переменные окружения.")
        return

    member_ids = await get_approved_member_ids()
    removed = 0
    for user_id in member_ids:
        try:
            member = await message.bot.get_chat_member(GROUP_ID, user_id)
            in_group = member.status in {"member", "administrator", "creator"}
        except Exception:
            in_group = False
        if not in_group:
            await delete_approved_member(user_id)
            removed += 1

    actor = message.from_user
    full_name = " ".join(filter(None, [actor.first_name, actor.last_name])).strip()
    await upsert_approved_member(actor.id, actor.username, full_name, intro_status="completed")
    await message.answer(
        "✅ Синхронизация завершена.\n"
        f"• Проверено участников: {len(member_ids)}\n"
        f"• Исключено из локального списка: {removed}\n\n"
        "Важно: Telegram Bot API не позволяет надёжно получить полный список всех участников группы, "
        "поэтому команда гарантированно очищает выбывших и актуализирует вызывающего пользователя."
    )