# обработка кнопок "Пойду", "Отказаться", "В резерв"

import asyncio
import logging
import time
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.keyboards import event_actions
from bot.texts import format_event_message
from bot.utils.helpers import get_username_by_id, get_user_mentions
from bot.config import GROUP_ID

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.callbacks import finalize_callback
from bot.utils.telegram_errors import safe_callback_answer
from bot.utils.roles import is_admin_or_owner
from bot.utils.design import brand_voice
from bot.filters.approved_member import approved_member_callback_only
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE

from bot.database import (
    get_event,
    add_participant,
    remove_participant,
    get_participants,
    get_main_participants,
    move_from_waitlist,
    add_driver,
    add_passenger,
    get_drivers_with_passengers,
    cancel_event,
)


# Состояния для ввода количества мест водителем
class CarpoolState(StatesGroup):
    seats = State()


logger = logging.getLogger(__name__)
router = Router()


PARTICIPATION_CALLBACK_RATE_LIMIT_SECONDS = 1.5
PARTICIPATION_CALLBACK_RATE_LIMIT_CACHE_TTL_SECONDS = 60.0
_participation_callback_hits: dict[tuple[int, int, str], float] = {}


def _is_participation_callback_rate_limited(
    user_id: int,
    event_id: int,
    action: str,
    *,
    now: float | None = None,
) -> bool:
    """Ограничивает частые клики по участию/резерву для одного события."""
    current_time = time.monotonic() if now is None else now
    if len(_participation_callback_hits) > 1000:
        stale_before = current_time - PARTICIPATION_CALLBACK_RATE_LIMIT_CACHE_TTL_SECONDS
        stale_keys = [
            cached_key
            for cached_key, cached_time in _participation_callback_hits.items()
            if cached_time < stale_before
        ]
        for stale_key in stale_keys:
            _participation_callback_hits.pop(stale_key, None)

    key = (int(user_id), int(event_id), action)
    previous_time = _participation_callback_hits.get(key)
    _participation_callback_hits[key] = current_time
    return bool(
        previous_time is not None
        and current_time - previous_time < PARTICIPATION_CALLBACK_RATE_LIMIT_SECONDS
    )


async def _answer_if_participation_rate_limited(
    callback: CallbackQuery,
    *,
    event_id: int,
    action: str,
) -> bool:
    if not _is_participation_callback_rate_limited(callback.from_user.id, event_id, action):
        return False
    await safe_callback_answer(callback, "⏱ Слишком частые нажатия. Подождите секунду.")
    return True


async def build_event_text(event_id: int, bot: Bot) -> str:
    event = await get_event(event_id)
    if not event:
        return "❌ Мероприятие не найдено."
    from bot.database import get_topic_name_by_thread_id
    going, waitlist, topic_name, drivers = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
        get_topic_name_by_thread_id(event.get("thread_id")),
        get_drivers_with_passengers(event_id),
    )
    responsible_id = event.get("responsible_id") or event["creator_id"]
    all_users = set(going + waitlist + [event["creator_id"], responsible_id])
    for driver in drivers:
        all_users.add(driver["user_id"])
        all_users.update(driver["passengers"])
    mentions = await get_user_mentions(all_users, bot)
    return await format_event_message(
        event,
        going,
        waitlist,
        mentions,
        topic_name=topic_name,
        organizer_mention=mentions.get(event["creator_id"]),
        responsible_mention=mentions.get(responsible_id),
    )

    
async def update_event_message(
    bot: Bot, event_id: int, thread_id: int, message_id: int
):
    event = await get_event(event_id)
    if not event:
        return

    from bot.database import get_topic_name_by_thread_id
    going, waitlist, drivers, topic_name = await asyncio.gather(
        get_main_participants(event_id),
        get_participants(event_id, "waitlist"),
        get_drivers_with_passengers(event_id),
        get_topic_name_by_thread_id(event.get("thread_id")),
    )

    responsible_id = event.get("responsible_id") or event["creator_id"]
    all_users = set(going + waitlist + [event["creator_id"], responsible_id])

    for driver in drivers:
        all_users.add(driver["user_id"])
        for p in driver["passengers"]:
            all_users.add(p)

    mentions = await get_user_mentions(all_users, bot)

    text = await format_event_message(
        event,
        going,
        waitlist,
        mentions,
        topic_name=topic_name,
        organizer_mention=mentions.get(event["creator_id"]),
        responsible_mention=mentions.get(responsible_id),
    )
    try:
        await bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=message_id,
            text=text,
            reply_markup=event_actions(event_id, event["carpool_enabled"]),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


@router.callback_query(F.data.startswith("join_"))
@approved_member_callback_only
async def join_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[1])
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
        await finalize_callback(callback, "Мест нет. Вы можете записаться в резерв", show_alert=True)
        return
    if user_id in waitlist:
        await finalize_callback(callback, "Вы уже в резерве. Откажитесь от резерва, чтобы записаться", show_alert=True)
        return
    if user_id in going:
        await finalize_callback(callback, "Вы уже записаны", show_alert=True)
        return
    await add_participant(event_id, user_id, "going")
    await safe_callback_answer(callback, brand_voice("participation_join"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("waitlist_"))
@approved_member_callback_only
async def waitlist_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[1])
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
        await finalize_callback(callback, "Вы уже в основном списке", show_alert=True)
        return
    if user_id in waitlist:
        await finalize_callback(callback, "Вы уже в резерве", show_alert=True)
        return
    await add_participant(event_id, user_id, "waitlist")
    await safe_callback_answer(callback, brand_voice("participation_waitlist"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("driver_"))
@approved_member_callback_only
async def become_driver(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    if await _answer_if_participation_rate_limited(callback, event_id=event_id, action="decline"):
        return
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    # Проверяем, не является ли уже водителем или пассажиром
    existing = await get_participants(event_id, "driver")
    if user_id in existing:
        await finalize_callback(callback, "Вы уже водитель", show_alert=True)
        return
    existing_pass = await get_participants(event_id, "passenger")
    if user_id in existing_pass:
        await finalize_callback(callback, "Вы уже пассажир. Откажитесь от места, чтобы стать водителем", show_alert=True)
        return
    # Запрашиваем количество мест
    await state.update_data(event_id=event_id)
    await state.set_state(CarpoolState.seats)
    try:
        await callback.bot.send_message(
            user_id,
            "Сколько свободных мест в вашей машине (включая вас)? Введите число:",
        )
    except TelegramForbiddenError:
        await finalize_callback(callback, "Не могу написать в ЛС. Откройте чат с ботом и нажмите Start.", show_alert=True)
        await state.clear()
        return
    await finalize_callback(callback)


@router.message(CarpoolState.seats)
async def process_car_seats(message: Message, state: FSMContext):
    try:
        seats = int(message.text)
        if seats < 1:
            await message.answer("Число мест должно быть больше 0. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("Введите число:")
        return
    data = await state.get_data()
    event_id = data["event_id"]
    user_id = message.from_user.id
    # Добавляем водителя
    success = await add_driver(event_id, user_id, seats)
    if not success:
        await message.answer(
            "Не удалось добавить водителя. Возможно, вы уже участвуете."
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
    await message.answer("Вы успешно добавлены как водитель!")
    await state.clear()


@router.callback_query(F.data.startswith("passenger_"))
@approved_member_callback_only
async def become_passenger(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event or event["status"] != "active":
        await finalize_callback(callback, "Мероприятие уже завершено или отменено", show_alert=True)
        return
    # Проверяем, не является ли уже водителем или пассажиром
    existing = await get_participants(event_id, "driver")
    if user_id in existing:
        await finalize_callback(callback, "Вы водитель. Чтобы стать пассажиром, сначала откажитесь от вождения.", show_alert=True)
        return
    existing_pass = await get_participants(event_id, "passenger")
    if user_id in existing_pass:
        await finalize_callback(callback, "Вы уже пассажир", show_alert=True)
        return
    # Получаем список водителей со свободными местами
    drivers = await get_drivers_with_passengers(event_id)
    if not drivers:
        await finalize_callback(callback, "Пока нет водителей. Станьте первым водителем!", show_alert=True)
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
            user_id, "Выберите водителя:", reply_markup=builder.as_markup()
        )
    except TelegramForbiddenError:
        await finalize_callback(callback, "Не могу написать в ЛС. Откройте чат с ботом и нажмите Start.", show_alert=True)
        return
    await finalize_callback(callback)


@router.callback_query(F.data.startswith("choose_driver_"))
@approved_member_callback_only
async def choose_driver(callback: CallbackQuery):
    parts = callback.data.split("_")
    event_id = int(parts[2])
    driver_id = int(parts[3])
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
    await safe_callback_answer(callback, "Вы успешно присоединились к водителю!")
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )


# Модифицируем функцию decline_event, чтобы учитывать удаление водителя и его пассажиров
@router.callback_query(F.data.startswith("decline_"))
async def decline_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    event = await get_event(event_id)
    if not event:
        await finalize_callback(callback, "Мероприятие не найдено", show_alert=True)
        return
    # Удаляем участника (и если водитель, то и всех его пассажиров)
    await remove_participant(event_id, user_id)
    # Уведомляем пассажиров, если удалён водитель (это делается в remove_participant, но можно добавить уведомления)
    # Для простоты уведомления не отправляем, но можно добавить
    # Освободилось место? Перемещаем из резерва
    moved_user = await move_from_waitlist(event_id)
    if moved_user:
        try:
            await callback.bot.send_message(
                moved_user,
                f"Освободилось место на мероприятии {event['title']}! Вы автоматически добавлены в основной список.",
            )
        except Exception as exc:
            logger.warning("Не удалось уведомить участника из резерва user_id=%s event_id=%s: %s", moved_user, event_id, exc)
    await safe_callback_answer(callback, brand_voice("participation_decline"))
    await update_event_message(
        callback.bot, event_id, event["thread_id"], event["message_id"]
    )


@router.callback_query(F.data.startswith("delete_"))
async def delete_event(callback: CallbackQuery):
    event_id = int(callback.data.split("_")[1])
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