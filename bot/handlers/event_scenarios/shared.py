import logging
import re
from datetime import date, datetime, time

import pytz
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.config import GROUP_ID, TIMEZONE
from bot.database import create_event, get_topic_name_by_thread_id, update_event_message_id, add_participant
from bot.constants import dedupe_categories
from bot.keyboards import event_actions, event_preview_keyboard
from bot.texts import format_event_message
from bot.utils.helpers import get_user_mention
from bot.utils.weather import get_weather
from bot.utils.ui import answer_private_final, answer_private_intermediate
from bot.utils.design import brand_voice, wizard_prompt

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)


class CreateEvent(StatesGroup):
    title = State()
    description = State()
    date = State()
    time = State()
    period_mode = State()
    period_end_date = State()
    period_end_time = State()
    duration = State()
    duration_unit = State()
    location = State()
    link = State()
    price_mode = State()
    price = State()
    limit = State()
    carpool = State()
    responsible = State()
    thread = State()
    category = State()
    preview = State()


EVENT_STEP_META = {
    CreateEvent.title.state: (1, 16, "📝 Название"),
    CreateEvent.description.state: (2, 16, "📄 Сюжет"),
    CreateEvent.date.state: (3, 16, "📅 Дата"),
    CreateEvent.time.state: (4, 16, "🕒 Время"),
    CreateEvent.period_mode.state: (5, 16, "📆 Повтор"),
    CreateEvent.period_end_date.state: (6, 16, "📆 Дата конца"),
    CreateEvent.period_end_time.state: (7, 16, "🕒 Время конца"),
    CreateEvent.duration.state: (8, 16, "⏱ Длительность"),
    CreateEvent.duration_unit.state: (8, 16, "⏱ Длительность"),
    CreateEvent.location.state: (9, 16, "📍 Маршрут"),
    CreateEvent.link.state: (10, 16, "🔗 Ссылка"),
    CreateEvent.price_mode.state: (11, 16, "💰 Расходы"),
    CreateEvent.price.state: (12, 16, "💰 Сумма"),
    CreateEvent.limit.state: (13, 16, "👥 Команда"),
    CreateEvent.carpool.state: (14, 16, "🚗 Попутка"),
    CreateEvent.responsible.state: (15, 16, "🧩 Ответственный"),
    CreateEvent.thread.state: (16, 16, "🗂 Публикация"),
    CreateEvent.category.state: (16, 16, "📂 Направление"),
    CreateEvent.preview.state: (16, 16, "👀 Превью"),
}


def event_step_prompt(state_name: str, text: str) -> str:
    """Добавляет прогресс мастера создания мероприятия к тексту шага."""
    step = EVENT_STEP_META.get(state_name)
    if not step:
        return text
    current, total, label = step
    return f"Шаг {current}/{total} · {label}\n\n{text}"


async def parse_datetime(text: str) -> datetime | None:
    """Парсит ДД.ММ.ГГГГ ЧЧ:ММ; дата в прошлом → None."""
    try:
        dt = datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")
        dt = TZ.localize(dt)
        if dt < datetime.now(TZ):
            return None
        return dt
    except ValueError:
        return None


def parse_date_only(text: str) -> date | None:
    """Парсит дату ДД.ММ.ГГГГ."""
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_time_only(text: str) -> time | None:
    """Парсит время ЧЧ:ММ."""
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def combine_local_datetime(day: date, clock: time) -> datetime:
    """Собирает aware-datetime в таймзоне бота."""
    return TZ.localize(datetime.combine(day, clock))


def normalize_event_link(text: str) -> str | None:
    """Нормализует URL; пустая строка → None; без схемы добавляет https://."""
    raw = (text or "").strip()
    if not raw or raw.lower() in {"пропустить", "skip", "-"}:
        return None
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = f"https://{raw}"
    if not re.match(r"^https?://[^\s]+\.[^\s]+", raw, flags=re.IGNORECASE):
        return None
    return raw


async def build_event_payload(
    state: FSMContext,
    category_value: str,
    creator_user_id: int,
) -> dict:
    """Собирает payload мероприятия из FSM для превью и публикации."""
    await state.update_data(category=category_value)
    data = await state.get_data()

    weather_info = ""
    if data.get("location"):
        weather = await get_weather(city=data["location"])
        if weather:
            weather_info = f"{weather['icon']} {weather['description']}, {weather['temp']}°C"

    return {
        "title": data["title"],
        "description": data.get("description"),
        "date_time": data["date_time"],
        "duration_minutes": data.get("duration_minutes"),
        "period_end": data.get("period_end"),
        "location": data.get("location"),
        "link": data.get("link") or "",
        "price_total": data.get("price_total"),
        "price_per_person": data.get("price_per_person"),
        "participant_limit": data.get("participant_limit"),
        "thread_id": data.get("thread_id"),
        "creator_id": creator_user_id,
        "responsible_id": data.get("responsible_id", creator_user_id),
        "weather_info": weather_info,
        "carpool_enabled": data.get("carpool_enabled", False),
        "category": category_value,
    }


async def show_event_preview(
    message: Message,
    state: FSMContext,
    user_id: int,
    bot,
) -> None:
    """Показывает превью карточки перед публикацией."""
    data = await state.get_data()
    selected_categories = dedupe_categories(data.get("selected_categories", []))
    if not selected_categories:
        raise ValueError("selected_categories_required")
    category_value = ",".join(selected_categories)
    event_data = await build_event_payload(state, category_value, user_id)
    organizer_mention = await get_user_mention(user_id, bot)
    responsible_id = event_data.get("responsible_id", user_id)
    responsible_mention = await get_user_mention(responsible_id, bot)
    topic_name = await get_topic_name_by_thread_id(event_data.get("thread_id"))
    preview_text = await format_event_message(
        {**event_data, "id": "preview"},
        [],
        [],
        {user_id: organizer_mention, responsible_id: responsible_mention},
        topic_name=topic_name,
        organizer_mention=organizer_mention,
        responsible_mention=responsible_mention,
    )
    await state.set_state(CreateEvent.preview)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.preview.state,
            f"{brand_voice('event_preview_intro')}\n\n{preview_text}",
        ),
        reply_markup=event_preview_keyboard(),
        parse_mode="HTML",
    )


async def finalize_event_creation(
    message: Message,
    state: FSMContext,
    category_value: str,
    creator_user_id: int,
):
    event_data = await build_event_payload(state, category_value, creator_user_id)
    data = await state.get_data()
    responsible_id = event_data.get("responsible_id", creator_user_id)
    event_id = await create_event(event_data)
    if responsible_id != creator_user_id:
        await add_participant(event_id, responsible_id, "going")

    bot = message.bot
    organizer_mention = await get_user_mention(creator_user_id, bot)
    responsible_mention = await get_user_mention(responsible_id, bot)
    mentions = {creator_user_id: organizer_mention, responsible_id: responsible_mention}
    topic_name = await get_topic_name_by_thread_id(data.get("thread_id"))

    event_text = await format_event_message(
        {**event_data, "id": event_id},
        [],
        [],
        mentions,
        topic_name=topic_name,
        organizer_mention=organizer_mention,
        responsible_mention=responsible_mention,
        show_cta=True,
    )

    try:
        from bot.utils.notifications import get_bot_start_url

        bot_start_url = await get_bot_start_url(bot)
        sent_msg = await bot.send_message(
            chat_id=GROUP_ID,
            text=event_text,
            message_thread_id=data.get("thread_id"),
            reply_markup=event_actions(
                event_id,
                data.get("carpool_enabled", False),
                bot_start_url=bot_start_url,
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await update_event_message_id(event_id, data.get("thread_id"), sent_msg.message_id)

        from bot.utils.scheduler import schedule_reminders_for_event
        from bot.utils.category_notify import notify_category_subscribers

        await schedule_reminders_for_event(event_id, bot)
        await notify_category_subscribers(
            bot,
            event_id=event_id,
            title=event_data["title"],
            category_value=category_value,
            creator_id=creator_user_id,
            message_id=sent_msg.message_id,
            thread_id=data.get("thread_id"),
        )

        link = f"https://t.me/c/{str(GROUP_ID).replace('-100', '')}/{sent_msg.message_id}"
        await answer_private_final(
            message,
            state,
            f"{brand_voice('event_created_private')}\n🚀 Тема: {topic_name or 'Основной чат'}\n🔗 {link}",
        )
        await state.clear()
    except Exception as exc:
        logger.error(f"Ошибка публикации: {exc}")
        await answer_private_final(message, state, f"❌ Ошибка публикации: {str(exc)[:200]}")
