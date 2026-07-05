import asyncio
from datetime import datetime, timedelta
from html import escape

import pytz

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import TIMEZONE, GROUP_ID
from bot.database import (
    get_user_events,
    get_event,
    get_participants,
    get_main_participants,
    get_topic_name_by_thread_id,
    set_event_responsible,
    set_driver,
    set_passenger,
    get_approved_member_ids,
    is_member_approved,
    get_user_id_by_username,
    add_participant,
)
from bot.keyboards import event_private_keyboard, my_events_keyboard, period_keyboard

from bot.texts import format_event_message
from bot.utils.helpers import get_user_mention, build_event_message_link, parse_int_arg
from bot.utils.callbacks import finalize_callback, parse_callback_split_int, parse_callback_suffix_int
from bot.utils.telegram_errors import ack_callback
from bot.utils.roles import is_admin_or_owner
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.handlers.event_scenarios.create import start_copy_event_wizard

router = Router()
TZ = pytz.timezone(TIMEZONE)


def _parse_manual_args(message: Message, expected_min: int) -> list[str] | None:
    parts = (message.text or "").split()
    if len(parts) < expected_min:
        return None
    return parts


async def _resolve_user_id(raw_user: str, message: Message) -> int | None:
    value = (raw_user or "").strip()
    if value.isdigit():
        return int(value)
    username = value.lstrip("@").lower()
    if not username:
        return None
    resolved = await get_user_id_by_username(username)
    if resolved:
        return int(resolved)    
    for uid in await get_approved_member_ids():
        try:
            chat = await message.bot.get_chat(uid)
        except Exception:
            continue
        if (getattr(chat, "username", "") or "").lower() == username:
            return int(uid)
    return None


async def _can_manage_event(event_id: int, user_id: int) -> tuple[bool, dict | None]:
    event = await get_event(event_id)
    if not event:
        return False, None
    if user_id == event["creator_id"] or is_admin_or_owner(user_id):
        return True, event
    return False, event


async def _can_view_event(event_id: int, user_id: int) -> tuple[bool, dict | None]:
    """Проверяет, может ли пользователь открыть карточку мероприятия в ЛС."""
    event = await get_event(event_id)
    if not event:
        return False, None

    if is_admin_or_owner(user_id):
        return True, event

    if user_id in {
        int(event["creator_id"]),
        int(event.get("responsible_id") or 0),
    }:
        return True, event

    going, waitlist = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
    )
    if user_id in going or user_id in waitlist:
        return True, event

    return False, event


@router.message(Command("my_events"))
async def cmd_my_events(message: Message):
    """Показывает список мероприятий пользователя с выбором периода."""
    await message.answer(
        "Выберите период для списка ваших мероприятий:",
        reply_markup=period_keyboard("my_events_period"),
    )


@router.callback_query(F.data.startswith("my_events_period_"))
async def my_events_with_period(callback: CallbackQuery):
    await ack_callback(callback)
    period = callback.data.removeprefix("my_events_period_")
    user_id = callback.from_user.id
    events = await get_user_events(user_id, status="active")

    now = datetime.now(TZ)
    period_days = {"week": 7, "month": 30}.get(period)
    future_border = now.replace(microsecond=0)
    future_limit = None if period_days is None else now + timedelta(days=period_days)

    filtered = []
    for event in events:
        dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
        if dt < future_border:
            continue
        if future_limit is not None and dt > future_limit:
            continue
        filtered.append(event)

    if not filtered:
        await callback.message.answer("📭 На выбранный период у вас нет активных мероприятий.")
        await finalize_callback(
            callback,
            delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
            skip_answer=True,
        )
        return

    title_map = {
        "week": "за неделю",
        "month": "за месяц",
        "all": "за всё время",
    }
    topic_names = await asyncio.gather(
        *(get_topic_name_by_thread_id(event.get("thread_id")) for event in filtered)
    )
    text_lines = [f"<b>📅 Ваши активные мероприятия {title_map.get(period, '')}:</b>"]
    for event, topic_name in zip(filtered, topic_names):
        dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
        date_str = dt.strftime("%d.%m.%Y %H:%M")
        topic_title = topic_name or "Основной чат"
        event_link = build_event_message_link(
            GROUP_ID, event.get("message_id"), event.get("thread_id")
        )
        link_text = (
            f'<a href="{event_link}">открыть сообщение</a>'
            if event_link
            else "недоступна"
        )

        text_lines.append(
            f"\n<b>{event['title']}</b>\n"
            f"🆔 ID: <code>{event['id']}</code>\n"
            f"🗓 {date_str}\n"
            f"🚀 Тема: {topic_title}\n"
            f"📍 {event.get('location') or 'не указано'}\n"
            f"🔗 Ссылка: {link_text}"
        )

    builder = InlineKeyboardBuilder()
    for event in filtered:
        builder.button(
            text=f"📋 Копия #{event['id']}",
            callback_data=f"copy_event_{event['id']}",
        )
    builder.adjust(1)

    await callback.message.answer(
        "\n".join(text_lines),
        parse_mode="HTML",
        reply_markup=my_events_keyboard(filtered),
    )
    if len(filtered) <= 10:
        copy_markup = builder.as_markup()
        if copy_markup.inline_keyboard:
            await callback.message.answer(
                "📋 Быстрое копирование прошлых встреч:",
                reply_markup=copy_markup,
            )
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )


@router.callback_query(F.data.startswith("copy_event_"))
async def copy_event_from_list(callback: CallbackQuery, state: FSMContext):
    await ack_callback(callback)
    raw_id = callback.data.removeprefix("copy_event_")
    if not raw_id.isdigit():
        await finalize_callback(callback, "Некорректный ID", show_alert=True)
        return

    event_id = int(raw_id)
    event = await get_event(event_id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id != event["creator_id"] and not is_admin_or_owner(user_id):
        await finalize_callback(callback, "Копировать может только создатель или админ", show_alert=True)
        return

    await start_copy_event_wizard(callback.message, state, event)
    await finalize_callback(
        callback,
        "Шаблон загружен — укажите новую дату",
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
    )


@router.callback_query(F.data.startswith("myevent_"))
async def show_my_event(callback: CallbackQuery):
    await ack_callback(callback)
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректный ID", show_alert=True)
        return

    allowed, event = await _can_view_event(event_id, callback.from_user.id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return
    if not allowed:
        await finalize_callback(callback, "Нет доступа к этому мероприятию", show_alert=True)
        return

    going, waitlist = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
    )

    user_id = callback.from_user.id
    from bot.handlers.participation import resolve_participation_status

    participation_status = resolve_participation_status(user_id, going, waitlist)
    can_manage, _ = await _can_manage_event(event_id, user_id)

    responsible_id = event.get("responsible_id") or event["creator_id"]
    all_users = sorted(set(going + waitlist + [event["creator_id"], responsible_id]))
    mention_values = await asyncio.gather(
        *(get_user_mention(uid, callback.bot) for uid in all_users)
    )
    mentions = dict(zip(all_users, mention_values))
    organizer_mention = mentions.get(event["creator_id"])
    responsible_mention = mentions.get(responsible_id)

    text = await format_event_message(
        event,
        going,
        waitlist,
        mentions,
        organizer_mention=organizer_mention,
        responsible_mention=responsible_mention,
        show_event_id=can_manage,
        show_cta=False,
    )
    await callback.message.answer(
        text,
        reply_markup=event_private_keyboard(
            event_id,
            bool(event["carpool_enabled"]),
            participation_status=participation_status,
            can_manage=can_manage,
        ),
        parse_mode="HTML",
    )
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )


@router.callback_query(F.data.startswith("manage_edit_"))
async def manage_edit_event(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.event_scenarios.edit import _can_edit_event, _show_edit_menu

    event_id = parse_callback_suffix_int(callback.data, prefix="manage_edit_")
    if event_id is None:
        await finalize_callback(callback, "Некорректный ID", show_alert=True)
        return
    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return
    if not allowed:
        await finalize_callback(callback, "🔒 Редактировать может только организатор, ответственный или админ", show_alert=True)
        return
    await state.update_data(edit_event_id=event_id, edit_selected_categories=[])
    await _show_edit_menu(callback.message, state, event_id)
    await finalize_callback(callback, "Редактирование открыто", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(Command("set_responsible"))
async def cmd_set_responsible(message: Message):
    parts = _parse_manual_args(message, expected_min=3)
    if not parts:
        await message.answer("Использование: /set_responsible <event_id> <user_id|@username>")
        return

    event_id = parse_int_arg(parts[1])
    if event_id is None:
        await message.answer("❌ event_id должен быть числом.")
        return
    responsible_id = await _resolve_user_id(parts[2], message)
    if not responsible_id:
        await message.answer("❌ Не удалось определить пользователя. Используйте user_id или @username.")
        return
    if not await is_member_approved(responsible_id):
        await message.answer("❌ Пользователь не является актуальным участником группы.")
        return
    allowed, event = await _can_manage_event(event_id, message.from_user.id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    if not allowed:
        await message.answer("❌ Только создатель или админ может назначать ответственного.")
        return

    await set_event_responsible(event_id, responsible_id)
    await add_participant(event_id, responsible_id, "going")
    from bot.handlers.participation import update_event_message
    await update_event_message(message.bot, event_id, event["thread_id"], event["message_id"])
    await message.answer("✅ Ответственный назначен и добавлен в основной список.")


@router.message(Command("add_participant_manual"))
async def cmd_add_participant_manual(message: Message):
    parts = _parse_manual_args(message, expected_min=3)
    if not parts:
        await message.answer("Использование: <code>/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;</code>", parse_mode="HTML")
        return

    event_id = parse_int_arg(parts[1])
    if event_id is None:
        await message.answer("❌ event_id должен быть числом.")
        return
    user_id = await _resolve_user_id(parts[2], message)
    if not user_id:
        await message.answer("❌ Не удалось определить пользователя. Используйте user_id или @username.")
        return
    if not await is_member_approved(user_id):
        await message.answer("❌ Пользователь не является актуальным участником группы.")
        return    
    status = parts[3].lower() if len(parts) > 3 else ""
    status_map = {"going": "going", "waitlist": "waitlist", "иду": "going", "резерв": "waitlist"}
    status = status_map.get(status, status)
    if status not in {"going", "waitlist"}:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Иду", callback_data=f"apm_going_{event_id}_{user_id}")
        kb.button(text="🕓 Резерв", callback_data=f"apm_waitlist_{event_id}_{user_id}")
        kb.adjust(2)
        await message.answer("Выберите статус кнопкой:", reply_markup=kb.as_markup())
        return

    allowed, event = await _can_manage_event(event_id, message.from_user.id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    if not allowed:
        await message.answer("❌ Только создатель или админ может вручную добавлять участников.")
        return

    created = await add_participant(event_id, user_id, status)
    from bot.handlers.participation import update_event_message
    await update_event_message(message.bot, event_id, event["thread_id"], event["message_id"])
    await message.answer("✅ Участник добавлен." if created else "ℹ️ Участник уже был в списке.")


@router.callback_query(F.data.startswith("apm_"))
async def cb_add_participant_manual_status(callback: CallbackQuery):
    _, status, event_raw, user_raw = callback.data.split("_", 3)
    event_id = int(event_raw)
    user_id = int(user_raw)
    allowed, event = await _can_manage_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа или событие не найдено", show_alert=True)
        return
    created = await add_participant(event_id, user_id, status)
    from bot.handlers.participation import update_event_message
    await update_event_message(callback.bot, event_id, event["thread_id"], event["message_id"])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Участник добавлен." if created else "ℹ️ Участник уже был в списке.")
    await finalize_callback(callback)

    
@router.message(Command("send_event_card"))
async def cmd_send_event_card(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /send_event_card <event_id>")
        return
    event_id = int(parts[1])
    event = await get_event(event_id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    allowed = (
        is_admin_or_owner(message.from_user.id)
        or message.from_user.id == event["creator_id"]
        or message.from_user.id == (event.get("responsible_id") or 0)
    )
    if not allowed:
        await message.answer("❌ Команда доступна организатору, ответственному или админу.")
        return
    dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    topic_name = await get_topic_name_by_thread_id(event.get("thread_id"))
    event_link = build_event_message_link(
        GROUP_ID, event.get("message_id"), event.get("thread_id")
    )
    link_text = (
        f'<a href="{event_link}">открыть основную карточку</a>'
        if event_link
        else "основная карточка недоступна"
    )
    text = (
        "📌 <b>Напоминание о мероприятии</b>\n"
        f"🆔 ID: <code>{event_id}</code>\n"
        f"Название: <b>{escape(str(event['title']))}</b>\n"
        f"🗓 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"📍 {escape(str(event.get('location') or 'не указано'))}\n"
        f"🚀 Тема: {escape(str(topic_name or 'Основной чат'))}\n"
        f"🔗 {link_text}"
    )
    sent = await message.bot.send_message(
        chat_id=event.get("chat_id") or GROUP_ID,
        message_thread_id=event.get("thread_id") or None,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await message.answer(f"✅ Короткое сообщение со ссылкой отправлено (message_id: {sent.message_id}).")


@router.message(Command("set_carpool_manual"))
async def cmd_set_carpool_manual(message: Message):
    parts = _parse_manual_args(message, expected_min=4)
    if not parts:
        await message.answer("Использование: /set_carpool_manual <event_id> <driver_id|@username> <seats>")
        return

    try:
        event_id = int(parts[1])
        seats = int(parts[3])
    except ValueError:
        await message.answer("❌ event_id и seats должны быть числами.")
        return
    driver_id = await _resolve_user_id(parts[2], message)
    if not driver_id:
        await message.answer("❌ Не удалось определить водителя. Используйте user_id или @username.")
        return
    if seats < 1:
        await message.answer("❌ Количество мест должно быть >= 1.")
        return

    allowed, event = await _can_manage_event(event_id, message.from_user.id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    if not allowed:
        await message.answer("❌ Только создатель или админ может настраивать карпулинг.")
        return

    ok = await set_driver(event_id, driver_id, seats)
    from bot.handlers.participation import update_event_message
    await update_event_message(message.bot, event_id, event["thread_id"], event["message_id"])
    await message.answer("✅ Водитель сохранён." if ok else "ℹ️ Водитель уже существует.")


@router.message(Command("add_passenger_manual"))
async def cmd_add_passenger_manual(message: Message):
    parts = _parse_manual_args(message, expected_min=4)
    if not parts:
        await message.answer("Использование: /add_passenger_manual <event_id> <passenger_id|@username> <driver_id|@username>")
        return

    try:
        event_id = int(parts[1])
    except ValueError:
        await message.answer("❌ event_id должен быть числом.")
        return
    passenger_id = await _resolve_user_id(parts[2], message)
    driver_id = await _resolve_user_id(parts[3], message)
    if not passenger_id or not driver_id:
        await message.answer("❌ Не удалось определить пассажира или водителя. Используйте user_id или @username.")
        return

    allowed, event = await _can_manage_event(event_id, message.from_user.id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    if not allowed:
        await message.answer("❌ Только создатель или админ может настраивать карпулинг.")
        return

    ok = await set_passenger(event_id, passenger_id, driver_id)
    from bot.handlers.participation import update_event_message
    await update_event_message(message.bot, event_id, event["thread_id"], event["message_id"])
    await message.answer("✅ Пассажир добавлен." if ok else "ℹ️ Не удалось добавить пассажира (проверьте места/дубликат).")