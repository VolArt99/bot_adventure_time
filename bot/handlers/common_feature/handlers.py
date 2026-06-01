from __future__ import annotations

from datetime import datetime, timezone
import logging
from html import escape
from urllib.parse import quote

import aiogram
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE

from bot.config import (
    ADMIN_DAILY_COMMAND_LIMIT,
    ADMIN_IDS,
    GROUP_ID,
    MEMBER_DAILY_COMMAND_LIMIT,
    OUTSIDER_START_DAILY_LIMIT,
    OWNER_CONTACT,
    OWNER_ID,
)
from bot.database import (
    add_pending_user,
    approve_pending_user,
    delete_pending_user,
    delete_approved_member,
    get_command_usage_summary,
    get_intro_members_statuses,
    get_or_create_user,
    get_pending_intro_members,
    get_pending_user,
    is_member_approved,
    update_intro_status,
    upsert_approved_member,
)
from bot.filters.admin import admin_only
from bot.filters.command_access import restricted_command
from bot.keyboards import (
    intro_status_keyboard,
    main_menu_keyboard,
    menu_section_keyboard,
    onboarding_start_keyboard,
    start_menu_keyboard,
    quick_event_templates_keyboard,
    rules_ack_keyboard,
)
from bot.texts import APPROVED_MEMBER_START_TEXT, GROUP_RULES_TEXT, ONBOARDING_WELCOME_TEXT

from .services import extract_command, is_user_in_group, notify_owner_about_request
from .views import build_command_action_text, build_help_text, build_main_menu_text, build_menu_section_text

logger = logging.getLogger(__name__)
router = Router()


def _owner_contact_html() -> str:
    """Контакт владельца для onboarding-сообщений."""
    if OWNER_CONTACT:
        if OWNER_CONTACT.startswith("@"):
            username = OWNER_CONTACT[1:]
            if username.replace("_", "").isalnum():
                return f'<a href="https://t.me/{quote(username)}">{escape(OWNER_CONTACT)}</a>'
        if OWNER_CONTACT.startswith("http://") or OWNER_CONTACT.startswith("https://"):
            safe_url = escape(OWNER_CONTACT, quote=True)
            return f'<a href="{safe_url}">контакт владельца</a>'
        return escape(OWNER_CONTACT)
    if OWNER_ID:
        return f'<a href="tg://user?id={OWNER_ID}">владельцу</a>'
    return "владельцу"


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])).strip()
    await get_or_create_user(user_id, username)
    if await is_user_in_group(message, user_id=user_id):
        await upsert_approved_member(user_id, username, full_name, intro_status="completed")
        await message.answer(
            APPROVED_MEMBER_START_TEXT,
            reply_markup=start_menu_keyboard(),
        )
        return

    await message.answer(ONBOARDING_WELCOME_TEXT, reply_markup=onboarding_start_keyboard())


@router.callback_query(F.data == "onboarding_start")
async def onboarding_start(callback: CallbackQuery):
    await callback.message.answer(GROUP_RULES_TEXT, reply_markup=rules_ack_keyboard())
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data == "rules_ack")
async def rules_ack(callback: CallbackQuery):
    user = callback.from_user
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    if await is_user_in_group(callback.message, user_id=user.id):
        await upsert_approved_member(user.id, user.username, full_name, intro_status="completed")
        await callback.message.answer("✅ Правила приняты. Вы уже участник группы, доступ открыт.")
    else:
        await add_pending_user(user.id, user.username, full_name)
        await notify_owner_about_request(callback)
        await callback.message.answer("✅ Правила приняты. Заявка отправлена владельцу на проверку.")
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(StateFilter(None), F.chat.type == "private", ~F.text.startswith("/"))
async def onboarding_guard(message: Message):
    command = extract_command(message)
    if command:
        return

    approved = await is_member_approved(message.from_user.id)
    if approved:
        return

    pending = await get_pending_user(message.from_user.id)
    if pending:
        await message.answer("⏳ Ваша заявка уже ожидает решения владельца.")
        return

    await message.answer(
        "Чтобы продолжить, нажмите «Старт», затем «Правила изучил(а) ❤️».\n"
        "Любые другие сообщения до этого шага недоступны.",
        reply_markup=onboarding_start_keyboard(),
    )


@router.callback_query(F.data.startswith("approve_user_"))
async def owner_approve_user(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await finalize_callback(callback, "Недостаточно прав", show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    pending = await approve_pending_user(user_id)
    if not pending:
        await finalize_callback(callback, "Заявка не найдена", show_alert=True)
        return

    try:
        invite = await callback.bot.create_chat_invite_link(chat_id=GROUP_ID, member_limit=1)
        await callback.bot.send_message(
            user_id,
            "✅ Ваша заявка одобрена. Ссылка для входа в группу:\n"
            f"{invite.invite_link}\n\n"
            f"Если возникнут вопросы — напишите {_owner_contact_html()}.",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning(
            "invite_send_failed user_id=%s command=%s event_id=%s error=%s",
            user_id,
            "approve_user",
            callback.id,
            type(exc).__name__,
        )

    await callback.message.edit_text(f"✅ Пользователь {user_id} одобрен и перенесён в контроль «Рассказа о себе».")
    await finalize_callback(callback, "Одобрено")


@router.callback_query(F.data.startswith("reject_user_"))
async def owner_reject_user(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await finalize_callback(callback, "Недостаточно прав", show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    await delete_pending_user(user_id)
    try:
        await callback.bot.send_message(user_id, "❌ К сожалению, заявка на вступление отклонена.")
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.info(
            "reject_notify_skipped user_id=%s command=%s event_id=%s error=%s",
            user_id,
            "reject_user",
            callback.id,
            type(exc).__name__,
        )

    await callback.message.edit_text(f"❌ Заявка пользователя {user_id} отклонена.")
    await finalize_callback(callback, "Отклонено")


@router.message(Command("pending_intro"))
async def cmd_pending_intro(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Эта команда доступна только владельцу.")
        return

    async def _filter_actual_members(members_list: list[dict]) -> list[dict]:
        actual_members: list[dict] = []
        for member in members_list:
            in_group = await is_user_in_group(message, user_id=int(member["user_id"]))
            if not in_group:
                await delete_approved_member(int(member["user_id"]))
                continue
            actual_members.append(member)
        return actual_members

    pending_members = await _filter_actual_members(await get_pending_intro_members())

    await message.answer(f"📋 В ожидании «Рассказа о себе»: {len(pending_members)}")
    for member in pending_members:
        username = f"@{member['username']}" if member.get("username") else "—"
        full_name = member.get("full_name") or "—"
        await message.answer(
            f"• ID: {member['user_id']}\n• Имя: {full_name}\n• Username: {username}",
            reply_markup=intro_status_keyboard(member["user_id"]),
        )

    members = await _filter_actual_members(await get_intro_members_statuses())
    if not members:
        await message.answer("Пока нет одобренных участников в группе.")
        return

    now = datetime.now(timezone.utc)
    lines = ["📊 Контроль «Рассказа о себе»:"]
    for m in members:
        if m.get("intro_status") == "completed":
            continue
        join_date = m.get("join_date")
        if isinstance(join_date, str):
            join_dt = datetime.fromisoformat(join_date.replace("Z", "+00:00"))
        else:
            join_dt = join_date
        days_passed = (now - join_dt).days if join_dt else 0
        days_left = max(0, 7 - days_passed)
        if days_passed <= 7:
            state = f"🟢 Всё хорошо (Осталось {days_left} дн.)"
        elif m.get("intro_status") == "pending":
            state = "🔴 Просрочено! Требуется проверка."
        else:
            state = "✅ Выполнено"

        username = f"@{m['username']}" if m.get("username") else "—"
        lines.append(f"• {m.get('full_name') or '—'} ({username}, id={m['user_id']}) — {state}")

    if len(lines) == 1:
        await message.answer("✅ Все одобренные участники уже добавили «Рассказ о себе».")
        return
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("intro_done_"))
async def intro_done(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await finalize_callback(callback, "Недостаточно прав", show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    await update_intro_status(user_id, "completed")
    await finalize_callback(callback, "Статус обновлён")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("intro_toggle_"))
async def intro_toggle(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await finalize_callback(callback, "Недостаточно прав", show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    members = await get_intro_members_statuses()
    current = next((m for m in members if int(m["user_id"]) == user_id), None)
    if not current:
        await finalize_callback(callback, "Пользователь не найден", show_alert=True)
        return

    new_status = "pending" if current.get("intro_status") == "completed" else "completed"
    await update_intro_status(user_id, new_status)
    await finalize_callback(callback, f"Статус: {new_status}")

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    is_admin_or_owner = message.from_user.id in ADMIN_IDS or message.from_user.id == OWNER_ID
    await message.answer(
        build_main_menu_text(is_admin_or_owner=is_admin_or_owner),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    is_admin_or_owner = message.from_user.id in ADMIN_IDS or message.from_user.id == OWNER_ID
    await message.answer(
        build_help_text(is_admin_or_owner=is_admin_or_owner),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
    )


@router.callback_query(F.data.startswith("menu_action_"))
async def menu_action_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data.removeprefix("menu_action_")
    user_id = callback.from_user.id
    is_admin_or_owner = user_id in ADMIN_IDS or user_id == OWNER_ID

    if action == "create_event":
        from bot.handlers.event_scenarios.create import start_create_event_wizard

        await start_create_event_wizard(callback.message, state)
        await finalize_callback(callback, "Мастер открыт", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    if action == "split_bill":
        from bot.handlers.split_bill_feature.handlers import start_split_bill_wizard

        await start_split_bill_wizard(callback.message, state, creator_id=user_id)
        await finalize_callback(callback, "Мастер открыт", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    if action == "my_events":
        from bot.keyboards import period_keyboard

        await callback.message.answer("Выберите период для списка ваших мероприятий:", reply_markup=period_keyboard("my_events_period"))
        await finalize_callback(callback, "Открыто")
        return

    if action == "digest":
        from bot.keyboards import period_keyboard

        await callback.message.answer("Выберите период для дайджеста:", reply_markup=period_keyboard("digest_period"))
        await finalize_callback(callback, "Открыто")
        return

    if action == "subscriptions":
        from bot.handlers.subscriptions import _subscriptions_keyboard
        from bot.database import get_user_category_subscriptions

        selected = await get_user_category_subscriptions(user_id)
        await callback.message.answer("📬 Выберите группы категорий для персонального дайджеста:", reply_markup=_subscriptions_keyboard(selected))
        await finalize_callback(callback, "Открыто")
        return

    if action == "my_digest":
        from bot.keyboards import period_keyboard

        await callback.message.answer("Выберите период для персонального дайджеста по вашим подпискам:", reply_markup=period_keyboard("my_digest"))
        await finalize_callback(callback, "Открыто")
        return

    if action in {"random_optin", "random_optout"}:
        from bot.database import set_random_meeting_opt_in

        await set_random_meeting_opt_in(user_id, action == "random_optin")
        text = "✅ Вы участвуете в рандомных встречах 1:1." if action == "random_optin" else "👌 Вы исключены из рандомных встреч 1:1."
        await callback.message.answer(text)
        await finalize_callback(callback, "Готово")
        return

    if action == "my_stats":
        from bot.database import get_user_stats

        stats = await get_user_stats(user_id)
        await callback.message.answer(
            "📊 <b>Ваша статистика</b>\n"
            f"• Уникальных мероприятий: <b>{stats.get('events_count', 0) or 0}</b>\n"
            f"• Подтверждённых участий: <b>{stats.get('total_participations', 0) or 0}</b>",
            parse_mode="HTML",
        )
        await finalize_callback(callback, "Готово")
        return

    if action == "top":
        from bot.database import get_top_participants
        from bot.utils.helpers import get_username_by_id

        top_users = await get_top_participants(days=30, limit=3)
        if not top_users:
            await callback.message.answer("🏆 За последние 30 дней пока нет данных по посещениям.")
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = ["🏆 <b>Топ-3 участников за 30 дней</b>"]
            for idx, item in enumerate(top_users, start=1):
                username = await get_username_by_id(item["user_id"], callback.bot) or f"id{item['user_id']}"
                lines.append(f"{medals[idx-1]} {escape(username)} — {item['participations']} участий")
            await callback.message.answer("\n".join(lines), parse_mode="HTML")
        await finalize_callback(callback, "Готово")
        return

    if action in {"roles", "usage_stats"}:
        if not is_admin_or_owner:
            await finalize_callback(callback, "Недостаточно прав", show_alert=True)
            return
        if action == "roles":
            await callback.message.answer(
                "🔐 <b>Роли и доступ</b>\n\n"
                f"👑 Владелец — полный доступ, без лимита.\n"
                f"🛡 Админ — все команды, лимит: {ADMIN_DAILY_COMMAND_LIMIT}/сутки.\n"
                f"🙋 Участник — пользовательские команды, лимит: {MEMBER_DAILY_COMMAND_LIMIT}/сутки.\n"
                f"🚪 Не участник — только /start, лимит: {OUTSIDER_START_DAILY_LIMIT}/сутки.",
                parse_mode="HTML",
            )
        else:
            rows = await get_command_usage_summary(days=7)
            if not rows:
                await callback.message.answer("📉 Пока нет статистики по использованию команд.")
            else:
                role_labels = {"owner": "владелец", "member": "участник", "outsider": "не участник", "admin": "администратор"}
                lines = ["📊 <b>Среднее использование команд (7 дней)</b>"]
                for row in rows:
                    role_name = role_labels.get(str(row["role"]).lower(), row["role"])
                    lines.append(f"• {role_name}: всего {row['total_commands']}, в среднем {row['avg_per_day']}/день")
                await callback.message.answer("\n".join(lines), parse_mode="HTML")
        await finalize_callback(callback, "Готово")
        return

    if action in {"admin_report", "send_events_list", "random_pairs"}:
        if not is_admin_or_owner:
            await finalize_callback(callback, "Недостаточно прав", show_alert=True)
            return
        if action == "admin_report":
            from bot.database import get_admin_report_metrics

            metrics = await get_admin_report_metrics()
            top_categories = metrics["top_categories"]
            categories_text = "\n".join(f"• {row['category']} — {row['cnt']}" for row in top_categories) if top_categories else "• пока нет данных"
            await callback.message.answer(
                "<b>Админ · отчёт</b>\n\n"
                f"Активные: <b>{metrics['active_events']}</b>\n"
                f"Средняя явка: <b>{metrics['avg_attendance']}</b>\n"
                f"No-show: <b>{metrics['no_show']}</b>\n\n"
                f"<b>Топ категорий</b>\n{categories_text}",
                parse_mode="HTML",
            )
        elif action == "send_events_list":
            from bot.keyboards import period_keyboard

            await callback.message.answer(
                "Выберите период для публикации списка мероприятий:",
                reply_markup=period_keyboard("broadcast_period"),
            )
        else:
            from bot.database import get_random_meeting_opt_in_users
            from bot.keyboards import random_pairs_topics_keyboard
            from bot.utils.topics import get_topics_list_from_db

            users = await get_random_meeting_opt_in_users()
            if len(users) < 2:
                await callback.message.answer("Недостаточно участников с согласием для 1:1.")
            else:
                topics = await get_topics_list_from_db()
                await callback.message.answer(
                    "Выберите группу/подгруппу, куда опубликовать random 1:1 пары:",
                    reply_markup=random_pairs_topics_keyboard(topics),
                )
        await finalize_callback(callback, "Готово")
        return

    text = build_command_action_text(action)
    if not text:
        await finalize_callback(callback, "Действие недоступно", show_alert=True)
        return
    await _replace_callback_message(
        callback,
        text,
        reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
    )
    await finalize_callback(callback, "Подсказка открыта")


async def _replace_callback_message(callback: CallbackQuery, text: str, *, reply_markup=None) -> None:
    """Редактирует текущее меню вместо отправки нового сообщения."""
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


@router.callback_query(F.data.startswith("menu_cmd_"))
async def menu_command_callback(callback: CallbackQuery):
    command_key = callback.data.removeprefix("menu_cmd_")
    text = build_command_action_text(command_key)
    if not text:
        await finalize_callback(callback, "Команда недоступна", show_alert=True)
        return
    is_admin_or_owner = callback.from_user.id in ADMIN_IDS or callback.from_user.id == OWNER_ID
    await _replace_callback_message(
        callback,
        text,
        reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
    )
    await finalize_callback(callback, "Команда открыта")


@router.callback_query(F.data.startswith("menu_"))
async def menu_callback(callback: CallbackQuery):
    section = callback.data.removeprefix("menu_")
    is_admin_or_owner = callback.from_user.id in ADMIN_IDS or callback.from_user.id == OWNER_ID
    if section == "home":
        await _replace_callback_message(
            callback,
            build_main_menu_text(is_admin_or_owner=is_admin_or_owner),
            reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
        )
        await finalize_callback(callback, "Главное меню")
        return
        
    text = build_menu_section_text(section, is_admin_or_owner=is_admin_or_owner)
    if not text:
        await finalize_callback(callback, "Раздел меню недоступен", show_alert=True)
        return

    reply_markup = (
        quick_event_templates_keyboard()
        if section == "quick"
        else menu_section_keyboard(section, is_admin_or_owner=is_admin_or_owner)
    )
    await _replace_callback_message(
        callback,
        text,
        reply_markup=reply_markup,
    )
    await finalize_callback(callback, "Раздел открыт")


@router.message(Command("roles"))
@admin_only
async def cmd_roles(message: Message):
    await message.answer(
        "🔐 <b>Роли и доступ</b>\n\n"
        f"👑 Владелец — полный доступ, без лимита.\n"
        f"🛡 Админ — все команды, лимит: {ADMIN_DAILY_COMMAND_LIMIT}/сутки.\n"
        f"🙋 Участник — только пользовательские команды, лимит: {MEMBER_DAILY_COMMAND_LIMIT}/сутки.\n"
        f"🚪 Не участник — только /start, лимит: {OUTSIDER_START_DAILY_LIMIT}/сутки.",
        parse_mode="HTML",
    )


@router.message(Command("usage_stats"))
@admin_only
async def cmd_usage_stats(message: Message):
    rows = await get_command_usage_summary(days=7)
    if not rows:
        await message.answer("📉 Пока нет статистики по использованию команд.")
        return
    lines = ["📊 <b>Среднее использование команд (последние 7 дней)</b>"]
    role_labels = {
        "owner": "владелец",
        "member": "участник",
        "outsider": "не участник",
        "admin": "администратор",
    }    
    for row in rows:
        role_name = role_labels.get(str(row["role"]).lower(), row["role"])
        lines.append(
            f"• {role_name}: всего {row['total_commands']}, "
            f"в среднем {row['avg_per_day']}/день"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    await message.answer("✅ Бот работает. Для списка возможностей используйте /help.")


@router.message(Command("debug_info"))
@restricted_command
async def cmd_debug_info(message: Message):
    from bot.config import ADMIN_IDS
    from bot.utils.topics import get_topics_list_from_db
    import sys

    try:
        me = await message.bot.get_me()
        chat = await message.bot.get_chat(GROUP_ID)
        member = await message.bot.get_chat_member(GROUP_ID, me.id)
        topics = await get_topics_list_from_db()
        is_admin = member.status in ["administrator", "creator"]
        is_forum = getattr(chat, "is_forum", False)

        text = (
            "🔎 <b>Диагностика бота</b>\n\n"
            f"🤖 Бот: @{me.username} (id: <code>{me.id}</code>)\n"
            f"📦 aiogram: <code>{aiogram.__version__}</code>\n"
            f"🐍 Python: <code>{sys.version.split()[0]}</code>\n\n"
            f"👥 Группа: <b>{chat.title}</b> (<code>{chat.id}</code>)\n"
            f"🧵 Форум включён: {'✅' if is_forum else '❌'}\n"
            f"🔐 Права админа у бота: {'✅' if is_admin else '❌'}\n"
            f"📚 Тем в БД: <b>{len(topics)}</b>\n\n"
            f"👤 Ваш id: <code>{message.from_user.id}</code>\n"
            f"🛡 Вы в ADMIN_IDS: {'✅' if message.from_user.id in ADMIN_IDS else '❌'}"
        )
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка диагностики: {e}")


@router.message(Command("list_topics"))
@restricted_command
async def list_topics(message: Message):
    from bot.utils.topics import get_topics_list_from_db

    topics = await get_topics_list_from_db()

    if not topics:
        await message.answer(
            "❌ Тем не обнаружено.\n\n"
            "📝 Как добавить темы:\n"
            "1. Откройте группу\n"
            "2. Создайте новую тему\n"
            "3. Отправьте сообщение в эту тему\n"
            "4. Бот автоматически обнаружит тему\n"
            "5. Используйте /list_topics снова"
        )
        return

    response = f"⚠️ Найдено тем: <b>{len(topics)}</b>\n\n"
    for topic in topics:
        response += f"🚀 <b>{topic['name']}</b> "
        response += f" ID темы: <code>{topic['message_thread_id']}</code>\n"

    await message.answer(response, parse_mode="HTML")


@router.message(Command("update_topic_names"))
@admin_only
async def update_topic_names(message: Message):
    from bot.database import get_all_topics

    await message.answer("⏳ Обновляю названия тем...")

    try:
        topics = await get_all_topics()
        updated_count = 0

        for topic in topics:
            if topic["name"].startswith("Тема "):
                logger.info("Требуется обновление названия для темы %s", topic["message_thread_id"])
                updated_count += 1

        await message.answer(f"✅ Проверено {len(topics)} тем\nОбновлено: {updated_count}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.callback_query(F.data == "cancel_create")
async def cancel_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await finalize_callback(
        callback,
        "Создание мероприятия отменено",
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        show_alert=True,
    )
