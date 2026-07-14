from __future__ import annotations

from datetime import datetime, timezone
import logging
from html import escape

import aiogram
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot.utils.callbacks import finalize_callback
from bot.utils.helpers import build_owner_contact_html
from bot.utils.design import brand_voice
from bot.utils.command_policy import can_view_command_hint
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.utils.roles import is_admin_or_owner as has_admin_or_owner, is_owner

from bot.config import (
    ADMIN_DAILY_COMMAND_LIMIT,
    GROUP_ID,
    MEMBER_DAILY_COMMAND_LIMIT,
    OUTSIDER_START_DAILY_LIMIT,
    OWNER_CONTACT,
    OWNER_ID,
    TIMEZONE,
)
from bot.database import (
    add_pending_user,
    approve_pending_user,
    delete_pending_user,
    delete_approved_member,
    get_command_usage_summary,
    get_intro_members_statuses,
    get_or_create_user,
    get_approved_member,
    get_pending_intro_members,
    get_pending_user,
    is_member_approved,
    update_intro_status,
    upsert_approved_member,
)
from bot.filters.admin import admin_only
from bot.filters.command_access import restricted_command
from bot.keyboards import (
    birthday_menu_keyboard,
    community_menu_keyboard,
    donation_keyboard,
    intro_status_keyboard,
    main_menu_keyboard,
    menu_section_keyboard,
    notification_settings_keyboard,
    onboarding_start_keyboard,
    start_menu_keyboard,
    quick_event_templates_keyboard,
    rules_ack_keyboard,
)

from .services import extract_command, is_user_in_group, notify_owner_about_request, notify_owner_about_member_start
from .views import (
    build_approval_message,
    build_approved_member_start_text,
    build_command_action_text,
    build_donation_text,
    build_donation_unavailable_text,
    build_group_member_bot_access_denied_text,
    build_group_rules_text,
    build_group_rules_full_text,
    build_help_text,
    build_main_menu_text,
    build_menu_section_text,
    build_notification_mode_text,
    build_not_enough_rights_text,
    build_onboarding_guard_text,
    build_onboarding_welcome_text,
    build_owner_only_text,
    build_pending_request_text,
    build_rejection_message,
    build_rules_accepted_existing_member_text,
    build_rules_accepted_pending_text,
)

logger = logging.getLogger(__name__)
router = Router()


def _owner_contact_html() -> str:
    """Контакт владельца для onboarding-сообщений."""
    return build_owner_contact_html(OWNER_CONTACT or "@Vol_Artem", OWNER_ID)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = " ".join(filter(None, [message.from_user.first_name, message.from_user.last_name])).strip()
    await get_or_create_user(user_id, username)
    try:
        if await is_user_in_group(message, user_id=user_id):
            if not await is_member_approved(user_id):
                await message.answer(
                    build_group_member_bot_access_denied_text(owner_contact_html=_owner_contact_html()),
                    parse_mode="HTML",
                )
                return

            existing = await get_approved_member(user_id)
            intro_status = "completed"
            if existing and existing.get("intro_status") == "pending":
                intro_status = "pending"
            await upsert_approved_member(user_id, username, full_name, intro_status=intro_status)
            if intro_status == "pending":
                await notify_owner_about_member_start(message)
            await message.answer(
                build_approved_member_start_text(),
                reply_markup=start_menu_keyboard(),
            )
            return

        await message.answer(build_onboarding_welcome_text(), reply_markup=onboarding_start_keyboard())
    except TelegramForbiddenError:
        logger.info("cmd_start skipped: user_id=%s blocked the bot", user_id)


@router.callback_query(F.data == "onboarding_start")
async def onboarding_start(callback: CallbackQuery):
    await callback.message.answer(build_group_rules_text(), reply_markup=rules_ack_keyboard())
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data == "rules_full")
async def rules_full(callback: CallbackQuery):
    await callback.message.answer(build_group_rules_full_text(), parse_mode="HTML")
    await finalize_callback(callback, "Полные правила")


@router.callback_query(F.data == "rules_ack")
async def rules_ack(callback: CallbackQuery):
    user = callback.from_user
    full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    if await is_user_in_group(callback.message, user_id=user.id):
        if not await is_member_approved(user.id):
            await callback.message.answer(
                build_group_member_bot_access_denied_text(owner_contact_html=_owner_contact_html()),
                parse_mode="HTML",
            )
        else:
            existing = await get_approved_member(user.id)
            intro_status = "completed" if existing and existing.get("intro_status") == "completed" else "pending"
            await upsert_approved_member(user.id, user.username, full_name, intro_status=intro_status)
            await callback.message.answer(build_rules_accepted_existing_member_text())
            if intro_status == "pending":
                await notify_owner_about_member_start(callback.message)
    else:
        await add_pending_user(user.id, user.username, full_name)
        await notify_owner_about_request(callback)
        await callback.message.answer(build_rules_accepted_pending_text())
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
        await message.answer(build_pending_request_text())
        return

    await message.answer(
        build_onboarding_guard_text(),
        reply_markup=onboarding_start_keyboard(),
    )


@router.callback_query(F.data.startswith("approve_user_"))
async def owner_approve_user(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await finalize_callback(callback, build_not_enough_rights_text(), show_alert=True)
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
            build_approval_message(
                invite_link=invite.invite_link,
                owner_contact_html=_owner_contact_html(),
            ),
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
    if not is_owner(callback.from_user.id):
        await finalize_callback(callback, build_not_enough_rights_text(), show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    await delete_pending_user(user_id)
    try:
        await callback.bot.send_message(user_id, build_rejection_message())
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
    if not is_owner(message.from_user.id):
        await message.answer(build_owner_only_text())
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
    if not is_owner(callback.from_user.id):
        await finalize_callback(callback, build_not_enough_rights_text(), show_alert=True)
        return

    user_id = int(callback.data.rsplit("_", 1)[-1])
    await update_intro_status(user_id, "completed")
    await finalize_callback(callback, "Статус обновлён")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("intro_toggle_"))
async def intro_toggle(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await finalize_callback(callback, build_not_enough_rights_text(), show_alert=True)
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

@router.message(Command("donate"))
async def cmd_donate(message: Message):
    keyboard = donation_keyboard()
    if not keyboard:
        await message.answer(build_donation_unavailable_text())
        return
    await message.answer(
        build_donation_text(),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    is_admin_or_owner = has_admin_or_owner(message.from_user.id)
    await message.answer(
        build_main_menu_text(is_admin_or_owner=is_admin_or_owner),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    is_admin_or_owner = has_admin_or_owner(message.from_user.id)
    await message.answer(
        build_help_text(is_admin_or_owner=is_admin_or_owner),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("menu_action_"))
async def menu_action_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data.removeprefix("menu_action_")
    user_id = callback.from_user.id
    is_admin_or_owner = has_admin_or_owner(user_id)

    if action == "donate":
        keyboard = donation_keyboard()
        if not keyboard:
            await callback.message.answer(build_donation_unavailable_text())
            await finalize_callback(callback, "Недоступно")
            return
        await callback.message.answer(
            build_donation_text(),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        await finalize_callback(callback, "Открыто")
        return

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

        await callback.message.answer("Выбери период для списка твоих мероприятий:", reply_markup=period_keyboard("my_events_period"))
        await finalize_callback(callback, "Открыто")
        return

    if action == "digest":
        from bot.keyboards import period_keyboard

        await callback.message.answer("Выбери период для дайджеста:", reply_markup=period_keyboard("digest_period"))
        await finalize_callback(callback, "Открыто")
        return

    if action == "subscriptions":
        from bot.handlers.subscriptions import SUBSCRIPTIONS_INTRO, _subscriptions_keyboard
        from bot.database import get_user_category_subscriptions

        selected = await get_user_category_subscriptions(user_id)
        await callback.message.answer(
            SUBSCRIPTIONS_INTRO,
            parse_mode="HTML",
            reply_markup=_subscriptions_keyboard(selected),
        )
        await finalize_callback(callback, "Открыто")
        return

    if action == "notification_mode":
        from bot.database import get_user_notification_settings

        current_mode = await get_user_notification_settings(user_id)
        await _replace_callback_message(
            callback,
            build_notification_mode_text(current_mode=current_mode),
            reply_markup=notification_settings_keyboard(current_mode=current_mode),
        )
        await finalize_callback(callback, "Открыто")
        return

    if action == "my_digest":
        from bot.keyboards import period_keyboard

        await callback.message.answer(
            "Выбери период для персонального дайджеста по твоим подпискам:",
            reply_markup=period_keyboard("my_digest"),
        )
        await finalize_callback(callback, "Открыто")
        return

    if action == "birthday":
        from bot.database import ensure_user_row, format_birthday_display, get_user_birth_date

        await ensure_user_row(user_id, callback.from_user.username)
        stored = await get_user_birth_date(user_id)
        if stored:
            display = format_birthday_display(stored)
            text = (
                f"🎂 Твой день рождения: <b>{display}</b>\n"
                f"{brand_voice('birthday_saved_hint')}\n\n"
                "Изменить: <code>/set_birthday ДД.ММ</code>"
            )
        else:
            text = (
                "🎂 День рождения ещё не указан.\n"
                "Добавь: <code>/set_birthday ДД.ММ</code> (год не нужен)."
            )
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=birthday_menu_keyboard(),
        )
        await finalize_callback(callback, "Открыто")
        return

    if action in {"random_optin", "random_optout"}:
        from bot.database import is_random_meeting_opt_in, set_random_meeting_opt_in

        await set_random_meeting_opt_in(user_id, action == "random_optin")
        is_opted = await is_random_meeting_opt_in(user_id)
        text = (
            "✅ Ты участвуешь в случайных встречах 1:1."
            if is_opted
            else "👌 Ты не участвуешь в случайных встречах 1:1."
        )
        await _replace_callback_message(
            callback,
            build_menu_section_text("community", is_admin_or_owner=is_admin_or_owner, random_opted_in=is_opted) or text,
            reply_markup=community_menu_keyboard(is_random_opted_in=is_opted),
        )
        await finalize_callback(callback, text)
        return

    if action == "my_stats":
        from bot.database import get_user_stats

        stats = await get_user_stats(user_id)
        await callback.message.answer(
            "📊 <b>Твоя статистика</b>\n"
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
            await finalize_callback(callback, "🔒 Эта команда доступна только организаторам и администраторам", show_alert=True)
            return
        if action == "roles":
            await callback.message.answer(
                "🔐 <b>Роли и доступ</b>\n\n"
                f"👑 Владелец — полный доступ, без лимита.\n"
                f"🛡 Админ — все команды, лимит: {ADMIN_DAILY_COMMAND_LIMIT}/сутки.\n"
                f"🙋 Участник — пользовательские команды, лимит: {MEMBER_DAILY_COMMAND_LIMIT}/сутки.\n"
                f"🚪 Не участник — только /start, лимит: {OUTSIDER_START_DAILY_LIMIT}/сутки.\n\n"
                f"<i>Сутки считаются по {TIMEZONE}. Callback-кнопки внутри мастеров не тратят лимит.</i>",
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
            await finalize_callback(callback, "🔒 Эта команда доступна только организаторам и администраторам", show_alert=True)
            return
        if action == "admin_report":
            from bot.database import get_admin_report_metrics

            metrics = await get_admin_report_metrics()
            top_categories = metrics["top_categories"]
            categories_text = "\n".join(
                f"• {escape(str(row['category']))} — {row['cnt']}" for row in top_categories
            ) if top_categories else "• пока нет данных"
            await callback.message.answer(
                "<b>Админ · отчёт</b>\n\n"
                f"Активные: <b>{metrics['active_events']}</b>\n"
                f"Средняя явка: <b>{metrics['avg_attendance']}</b>\n\n"
                f"<b>Топ категорий</b>\n{categories_text}",
                parse_mode="HTML",
            )
        elif action == "send_events_list":
            from bot.keyboards import period_keyboard

            await callback.message.answer(
                "Выбери период для публикации списка мероприятий:",
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
                    "Выбери группу/подгруппу, куда опубликовать случайные пары 1:1:",
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


@router.callback_query(F.data.startswith("notify_"))
async def notification_mode_callback(callback: CallbackQuery):
    mode = callback.data.removeprefix("notify_")
    if mode not in {"all", "mine", "off"}:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return

    from bot.database import get_user_notification_settings, set_user_notification_settings

    user_id = callback.from_user.id
    await set_user_notification_settings(user_id, mode)
    current_mode = await get_user_notification_settings(user_id)
    await _replace_callback_message(
        callback,
        build_notification_mode_text(current_mode=current_mode),
        reply_markup=notification_settings_keyboard(current_mode=current_mode),
    )
    await finalize_callback(callback, brand_voice("notification_mode_saved"))


@router.callback_query(F.data.startswith("menu_cmd_"))
async def menu_command_callback(callback: CallbackQuery):
    command_key = callback.data.removeprefix("menu_cmd_")
    user_id = callback.from_user.id
    is_admin_or_owner = has_admin_or_owner(user_id)
    is_approved = await is_member_approved(user_id)
    if not can_view_command_hint(
        command_key,
        user_id,
        is_approved_member=is_approved,
    ):
        await finalize_callback(callback, "🔒 Эта команда доступна только организаторам и администраторам", show_alert=True)
        return

    text = build_command_action_text(command_key)
    if not text:
        await finalize_callback(callback, "Команда недоступна", show_alert=True)
        return
    await _replace_callback_message(
        callback,
        text,
        reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
    )
    await finalize_callback(callback, "Команда открыта")


@router.callback_query(F.data.startswith("menu_"))
async def menu_callback(callback: CallbackQuery):
    section = callback.data.removeprefix("menu_")
    user_id = callback.from_user.id
    is_admin_or_owner = has_admin_or_owner(user_id)
    if section == "home":
        await _replace_callback_message(
            callback,
            build_main_menu_text(is_admin_or_owner=is_admin_or_owner),
            reply_markup=main_menu_keyboard(is_admin_or_owner=is_admin_or_owner),
        )
        await finalize_callback(callback, "Главное меню")
        return

    if section == "community":
        from bot.database import is_random_meeting_opt_in

        is_opted = await is_random_meeting_opt_in(user_id)
        text = build_menu_section_text(
            "community",
            is_admin_or_owner=is_admin_or_owner,
            random_opted_in=is_opted,
        )
        if not text:
            await finalize_callback(callback, "Раздел меню недоступен", show_alert=True)
            return
        await _replace_callback_message(
            callback,
            text,
            reply_markup=community_menu_keyboard(is_random_opted_in=is_opted),
        )
        await finalize_callback(callback, "Раздел открыт")
        return

    if section == "notification_mode":
        from bot.database import get_user_notification_settings

        current_mode = await get_user_notification_settings(user_id)
        await _replace_callback_message(
            callback,
            build_notification_mode_text(current_mode=current_mode),
            reply_markup=notification_settings_keyboard(current_mode=current_mode),
        )
        await finalize_callback(callback, "Раздел открыт")
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
        f"🚪 Не участник — только /start, лимит: {OUTSIDER_START_DAILY_LIMIT}/сутки.\n\n"
        f"<i>Сутки считаются по {TIMEZONE}. Callback-кнопки внутри мастеров не тратят лимит.</i>",
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
    from bot.utils.design import brand_voice

    await message.answer(brand_voice("status_online"))


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
        await message.answer(f"❌ Ошибка диагностики: {escape(str(e))}")


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
        safe_name = escape(str(topic["name"]))
        response += f"🚀 <b>{safe_name}</b> "
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
    current_state = await state.get_state() or ""
    await state.clear()
    cancel_text = (
        brand_voice("split_bill_cancel")
        if current_state.startswith("SplitBillCreate:")
        else brand_voice("wizard_cancel")
    )
    await finalize_callback(
        callback,
        cancel_text,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        show_alert=True,
    )
