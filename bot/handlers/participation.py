# обработка кнопок "Пойду", "Отказаться", "В резерв"

import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.keyboards import event_actions, event_delete_confirm_keyboard, event_manage_keyboard
from bot.texts import format_event_message
from bot.utils.helpers import get_username_by_id, get_user_mentions
from bot.config import GROUP_ID

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.callbacks import finalize_callback, parse_callback_split_int, parse_callback_suffix_int
from bot.utils.telegram_errors import safe_callback_answer
from bot.utils.roles import is_admin_or_owner
from bot.utils.design import brand_voice
from bot.filters.approved_member import approved_member_callback_only
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.utils.callback_rate_limit import answer_if_callback_rate_limited

from bot.database import (
    get_event,
    add_participant,
    remove_participant,
    get_participants,
    get_main_participants,
    get_ride_seekers,
    move_from_waitlist,
    add_driver,
    add_passenger,
    get_drivers_with_passengers,
    cancel_event,
    toggle_ride_seeker,
    set_attendance_response,
    get_attendance_summary,
)


# Состояния для ввода количества мест водителем
class CarpoolState(StatesGroup):
    seats = State()


logger = logging.getLogger(__name__)
router = Router()


def resolve_participation_status(user_id: int, going: list[int], waitlist: list[int]) -> str | None:
    if user_id in going:
        return "going"
    if user_id in waitlist:
        return "waitlist"
    return None


PARTICIPATION_CALLBACK_RATE_LIMIT_SECONDS = 1.5


async def _answer_if_participation_rate_limited(
    callback: CallbackQuery,
    *,
    event_id: int,
    action: str,
) -> bool:
    return await answer_if_callback_rate_limited(
        callback,
        scope="participation",
        resource_id=event_id,
        action=action,
        cooldown_seconds=PARTICIPATION_CALLBACK_RATE_LIMIT_SECONDS,
    )


async def _collect_event_card_context(event_id: int, bot: Bot) -> tuple[dict | None, str, dict]:
    """Общий сбор данных для карточки мероприятия."""
    event = await get_event(event_id)
    if not event:
        return None, "❌ Мероприятие не найдено.", {}

    from bot.database import get_topic_name_by_thread_id

    main_ids, waitlist, topic_name, drivers, ride_seekers = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
        get_topic_name_by_thread_id(event.get("thread_id")),
        get_drivers_with_passengers(event_id),
        get_ride_seekers(event_id),
    )
    seeker_set = set(ride_seekers)
    going = [uid for uid in main_ids if uid not in seeker_set]
    responsible_id = event.get("responsible_id") or event["creator_id"]
    all_users = set(going + waitlist + ride_seekers + [event["creator_id"], responsible_id])
    for driver in drivers:
        all_users.add(driver["user_id"])
        all_users.update(driver["passengers"])
    mentions = await get_user_mentions(all_users, bot)
    text = await format_event_message(
        event,
        going,
        waitlist,
        mentions,
        topic_name=topic_name,
        organizer_mention=mentions.get(event["creator_id"]),
        responsible_mention=mentions.get(responsible_id),
        show_cta=True,
    )
    return event, text, {
        "going": going,
        "waitlist": waitlist,
        "drivers": drivers,
        "ride_seekers": ride_seekers,
        "topic_name": topic_name,
        "mentions": mentions,
    }


async def build_event_text(event_id: int, bot: Bot) -> str:
    _, text, _ = await _collect_event_card_context(event_id, bot)
    return text


async def update_event_message(
    bot: Bot, event_id: int, thread_id: int, message_id: int
):
    event, text, _ = await _collect_event_card_context(event_id, bot)
    if not event:
        return

    from bot.utils.notifications import get_bot_start_url

    bot_start_url = await get_bot_start_url(bot)
    try:
        await bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=message_id,
            text=text,
            reply_markup=event_actions(
                event_id,
                event["carpool_enabled"],
                bot_start_url=bot_start_url,
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _attendance_reply_text(event_id: int, *, confirmed: bool) -> str:
    summary = await get_attendance_summary(event_id)
    confirmed_n = int(summary.get("confirmed") or 0)
    pending_n = int(summary.get("pending") or 0)
    declined_n = int(summary.get("declined") or 0)
    prefix = "✅ Участие подтверждено" if confirmed else "Тебя сняли со списка участников"
    return (
        f"{prefix}\n"
        f"Сводка: ✅ {confirmed_n} · ⏳ {pending_n} · ❌ {declined_n}"
    )


@router.callback_query(F.data.startswith("join_"))
@approved_member_callback_only
async def join_event(callback: CallbackQuery):
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    if await _answer_if_participation_rate_limited(callback, event_id=event_id, action="join"):
        return
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    going, waitlist = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
    )
    if event["participant_limit"] and len(going) >= event["participant_limit"]:
        await finalize_callback(callback, "Мест нет. Можешь записаться в резерв", show_alert=True)
        return
    if user_id in waitlist:
        await finalize_callback(callback, "Ты уже в резерве. Откажись от резерва, чтобы записаться", show_alert=True)
        return
    if user_id in going:
        await finalize_callback(callback, "Ты уже записан", show_alert=True)
        return
    added = await add_participant(event_id, user_id, "going")
    if not added:
        await finalize_callback(
            callback,
            "Не удалось записаться: мест нет или ты уже в списке",
            show_alert=True,
        )
        return
    await safe_callback_answer(callback, brand_voice("participation_join"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("waitlist_"))
@approved_member_callback_only
async def waitlist_event(callback: CallbackQuery):
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    if await _answer_if_participation_rate_limited(callback, event_id=event_id, action="waitlist"):
        return
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    going, waitlist = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
    )
    if user_id in going:
        await finalize_callback(callback, "Ты уже в основном списке", show_alert=True)
        return
    if user_id in waitlist:
        await finalize_callback(callback, "Ты уже в резерве", show_alert=True)
        return
    added = await add_participant(event_id, user_id, "waitlist")
    if not added:
        await finalize_callback(callback, "Ты уже в списке участников", show_alert=True)
        return
    waitlist_after = await get_participants(event_id, "waitlist")
    position = waitlist_after.index(user_id) + 1 if user_id in waitlist_after else len(waitlist_after)
    await safe_callback_answer(
        callback,
        brand_voice("participation_waitlist_position").format(position=position),
    )
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("seek_ride_"))
@approved_member_callback_only
async def seek_ride_toggle(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="seek_ride_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    if await _answer_if_participation_rate_limited(callback, event_id=event_id, action="seek_ride"):
        return
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    if not event.get("carpool_enabled"):
        await finalize_callback(callback, "Карпулинг не включён", show_alert=True)
        return

    result = await toggle_ride_seeker(event_id, user_id)
    messages = {
        "added": brand_voice("carpool_seek_added"),
        "removed": brand_voice("carpool_seek_removed"),
        "denied": "Недоступно для водителей и пассажиров",
        "full": "Мест нет. Запишись в резерв",
    }
    await safe_callback_answer(callback, messages.get(result, "Готово"))
    if result in {"added", "removed"}:
        await update_event_message(
            callback.bot, event_id, event["thread_id"], event["message_id"]
        )


@router.callback_query(F.data.startswith("confirm_attendance_"))
@approved_member_callback_only
async def confirm_attendance(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="confirm_attendance_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие недоступно", show_alert=True)
        return
    main = await get_main_participants(event_id)
    if user_id not in main:
        await finalize_callback(callback, "Тебя нет в списке участников", show_alert=True)
        return
    await set_attendance_response(event_id, user_id, "confirmed")
    await finalize_callback(callback, await _attendance_reply_text(event_id, confirmed=True))


@router.callback_query(F.data.startswith("decline_attendance_"))
@approved_member_callback_only
async def decline_attendance(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="decline_attendance_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие недоступно", show_alert=True)
        return
    main = await get_main_participants(event_id)
    if user_id not in main:
        await finalize_callback(callback, "Тебя нет в списке участников", show_alert=True)
        return
    await set_attendance_response(event_id, user_id, "declined")
    removed = await remove_participant(event_id, user_id)
    moved_user = await move_from_waitlist(event_id) if removed else None
    if moved_user:
        from bot.utils.notifications import send_private_dm

        await send_private_dm(
            callback.bot,
            moved_user,
            brand_voice("waitlist_promoted").format(title=event["title"]),
            parse_mode=None,
            notification_kind="personal",
        )
    if event.get("message_id"):
        await update_event_message(
            callback.bot, event_id, event["thread_id"], event["message_id"]
        )
    await finalize_callback(callback, await _attendance_reply_text(event_id, confirmed=False))


@router.callback_query(F.data.startswith("driver_"))
@approved_member_callback_only
async def become_driver(callback: CallbackQuery, state: FSMContext):
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    if await _answer_if_participation_rate_limited(callback, event_id=event_id, action="driver"):
        return
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    # Проверяем, не является ли уже водителем или пассажиром
    existing = await get_participants(event_id, "driver")
    if user_id in existing:
        await finalize_callback(callback, "Ты уже водитель", show_alert=True)
        return
    existing_pass = await get_participants(event_id, "passenger")
    if user_id in existing_pass:
        await finalize_callback(callback, "Ты уже пассажир. Откажись от места, чтобы стать водителем", show_alert=True)
        return
    # Запрашиваем количество мест
    await state.update_data(event_id=event_id)
    await state.set_state(CarpoolState.seats)
    try:
        await callback.bot.send_message(
            user_id,
            brand_voice("carpool_driver_seats"),
        )
    except TelegramForbiddenError:
        await finalize_callback(callback, "Не могу написать в ЛС. Открой чат с ботом и нажми Start.", show_alert=True)
        await state.clear()
        return
    await finalize_callback(callback)


@router.message(CarpoolState.seats)
async def process_car_seats(message: Message, state: FSMContext):
    try:
        seats = int(message.text)
        if seats < 1:
            await message.answer("Число мест должно быть больше 0. Попробуй ещё раз:")
            return
    except ValueError:
        await message.answer("Введи число:")
        return
    data = await state.get_data()
    event_id = data["event_id"]
    user_id = message.from_user.id
    # Добавляем водителя
    success = await add_driver(event_id, user_id, seats)
    if not success:
        await message.answer(
            "Не удалось добавить водителя. Возможно, ты уже участвуешь."
        )
        await state.clear()
        return
    # Добавляем водителя в основной список, если его там нет
    going = await get_main_participants(event_id)
    if user_id not in going:
        await add_participant(event_id, user_id, "going")
    # Обновляем сообщение мероприятия
    event = await get_event(event_id)
    await update_event_message(
        message.bot, event_id, event["thread_id"], event["message_id"]
    )
    await message.answer(brand_voice("carpool_driver_added"))
    await state.clear()


@router.callback_query(F.data.startswith("passenger_"))
@approved_member_callback_only
async def become_passenger(callback: CallbackQuery):
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    # Проверяем, не является ли уже водителем или пассажиром
    existing = await get_participants(event_id, "driver")
    if user_id in existing:
        await finalize_callback(callback, "Ты водитель. Чтобы стать пассажиром, сначала откажись от вождения.", show_alert=True)
        return
    existing_pass = await get_participants(event_id, "passenger")
    if user_id in existing_pass:
        await finalize_callback(callback, "Ты уже пассажир", show_alert=True)
        return
    # Получаем список водителей со свободными местами
    drivers = await get_drivers_with_passengers(event_id)
    if not drivers:
        await finalize_callback(callback, "Пока нет водителей. Стань первым! 🚗", show_alert=True)
        return
    # Формируем клавиатуру выбора водителя
    builder = InlineKeyboardBuilder()
    has_free_drivers = False
    for driver in drivers:
        free = driver["car_seats"] - len(driver["passengers"])
        if free > 0:
            has_free_drivers = True
            # Получаем username водителя
            username = await get_username_by_id(driver["user_id"], callback.bot) or str(
                driver["user_id"]
            )
            builder.button(
                text=f"{username} ({free} мест)",
                callback_data=f"choose_driver_{event_id}_{driver['user_id']}",
            )
    if not has_free_drivers:
        await finalize_callback(callback, "Нет свободных мест у водителей", show_alert=True)
        return
    builder.adjust(1)
    try:
        await callback.bot.send_message(
            user_id, brand_voice("carpool_choose_driver"), reply_markup=builder.as_markup()
        )
    except TelegramForbiddenError:
        await finalize_callback(callback, "Не могу написать в ЛС. Открой чат с ботом и нажми Start.", show_alert=True)
        return
    await finalize_callback(callback)


@router.callback_query(F.data.startswith("choose_driver_"))
@approved_member_callback_only
async def choose_driver(callback: CallbackQuery):
    event_id = parse_callback_split_int(callback.data, index=2, min_parts=4)
    driver_id = parse_callback_split_int(callback.data, index=3, min_parts=4)
    if event_id is None or driver_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    # Добавляем пассажира
    success = await add_passenger(event_id, user_id, driver_id)
    if not success:
        await finalize_callback(callback, "Не удалось добавить пассажира. Возможно, места уже заняты.", show_alert=True)
        return
    # Добавляем пассажира в основной список, если его там нет
    going = await get_main_participants(event_id)
    if user_id not in going:
        await add_participant(event_id, user_id, "going")
    # Обновляем сообщение
    event = await get_event(event_id)
    await safe_callback_answer(callback, brand_voice("carpool_passenger_added"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )


# Модифицируем функцию decline_event, чтобы учитывать удаление водителя и его пассажиров
@router.callback_query(F.data.regexp(r"^decline_\d+$"))
@approved_member_callback_only
async def decline_event(callback: CallbackQuery):
    event_id = parse_callback_split_int(callback.data, index=1, min_parts=2)
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return
    removed = await remove_participant(event_id, user_id)
    if not removed:
        await finalize_callback(callback, "Тебя нет в записи на это мероприятие", show_alert=True)
        return
    moved_user = await move_from_waitlist(event_id)
    if moved_user:
        from bot.utils.notifications import send_private_dm

        await send_private_dm(
            callback.bot,
            moved_user,
            brand_voice("waitlist_promoted").format(title=event["title"]),
            parse_mode=None,
            notification_kind="personal",
        )
    await safe_callback_answer(callback, brand_voice("participation_decline"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("delete_confirm_"))
async def delete_event_confirm(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="delete_confirm_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    event = await get_event(event_id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return

    user_id = callback.from_user.id
    is_creator = user_id == event["creator_id"]
    is_admin = is_admin_or_owner(user_id)
    if not is_creator and not is_admin:
        await finalize_callback(callback, "Удалять мероприятие может только организатор или администратор.", show_alert=True)
        return

    await callback.message.answer(
        "⚠️ <b>Удалить мероприятие навсегда?</b>\n"
        "Карточка в группе будет удалена, участники не получат отдельного уведомления.",
        parse_mode="HTML",
        reply_markup=event_delete_confirm_keyboard(event_id),
    )
    await finalize_callback(callback)


@router.callback_query(F.data.startswith("delete_cancel_"))
async def delete_event_cancel(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="delete_cancel_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=event_manage_keyboard(event_id))
    await finalize_callback(callback, "Удаление отменено")


@router.callback_query(F.data.startswith("delete_execute_"))
async def delete_event_execute(callback: CallbackQuery):
    event_id = parse_callback_suffix_int(callback.data, prefix="delete_execute_")
    if event_id is None:
        await finalize_callback(callback, "Некорректные данные", show_alert=True)
        return
    event = await get_event(event_id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return

    user_id = callback.from_user.id
    is_creator = user_id == event["creator_id"]
    is_admin = is_admin_or_owner(user_id)
    if not is_creator and not is_admin:
        await finalize_callback(callback, "Удалять мероприятие может только организатор или администратор.", show_alert=True)
        return

    await safe_callback_answer(callback, "Мероприятие удалено")
    await cancel_event(event_id)

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    try:
        await callback.bot.delete_message(
            chat_id=GROUP_ID,
            message_id=event["message_id"],
        )
    except Exception:
        await callback.bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=event["message_id"],
            text="❌ Мероприятие удалено организатором/администратором.",
        )