from aiogram import F, Router
from datetime import datetime, timedelta
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
import pytz

from bot.config import TIMEZONE

from bot.constants import CARPOOL_HELP_TEXT, EVENT_CATEGORY_GROUPS, dedupe_categories
from bot.filters.registered_user import registered_user_only
from bot.keyboards import (
    cancel_keyboard,
    skip_field_keyboard,
    carpool_keyboard,
    event_period_mode_keyboard,
    event_price_mode_keyboard,
    category_groups_keyboard,
    choose_topic_keyboard,
    event_preview_keyboard,
    template_field_keyboard,
    event_datetime_keyboard,
)
from .shared import CreateEvent, event_step_prompt, parse_datetime, build_event_payload
from bot.utils.design import wizard_prompt, brand_voice
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.utils.ui import answer_private_intermediate, err
from bot.utils.topics import get_topics_list_from_db
from bot.texts import format_event_message
from bot.utils.helpers import get_user_mention

router = Router(name=__name__)
TZ = pytz.timezone(TIMEZONE)


def _datetime_example_text() -> str:
    example = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    return (
        f"{wizard_prompt('datetime')}\n"
        f"Пример: <b>{example}</b>"
    )


async def _advance_after_datetime(message: Message, state: FSMContext, dt: datetime) -> None:
    await state.update_data(date_time=dt.isoformat())
    data = await state.get_data()
    if data.get("from_copy"):
        topics = await get_topics_list_from_db()
        if topics:
            await state.set_state(CreateEvent.thread)
            await answer_private_intermediate(
                message,
                state,
                event_step_prompt(CreateEvent.thread.state, "🗂 Выберите, где опубликовать копию мероприятия:"),
                reply_markup=choose_topic_keyboard(topics, back_callback="event_back"),
            )
            return
        await state.update_data(thread_id=None)
        from .shared import show_event_preview

        await show_event_preview(message, state, message.from_user.id, message.bot)
        return

    await state.update_data(period_end=None)
    await state.set_state(CreateEvent.period_mode)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.period_mode.state,
            f"{wizard_prompt('period_mode')}\n"
            "Например: книжный клуб читает книгу с даты старта до даты дедлайна.",
        ),
        reply_markup=event_period_mode_keyboard(back_callback="event_back"),
    )


def _quick_datetime(choice: str) -> datetime:
    now = datetime.now(TZ)
    if choice == "event_dt_tonight":
        candidate = now.replace(hour=19, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if choice == "event_dt_tomorrow":
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=19, minute=0, second=0, microsecond=0)
    days_until_saturday = (5 - now.weekday()) % 7
    if days_until_saturday == 0 and now.hour >= 12:
        days_until_saturday = 7
    saturday = now + timedelta(days=days_until_saturday)
    return saturday.replace(hour=12, minute=0, second=0, microsecond=0)

async def start_create_event_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEvent.title)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.title.state, wizard_prompt("title")),
        reply_markup=cancel_keyboard(),
    )


async def start_copy_event_wizard(message: Message, state: FSMContext, source_event: dict) -> None:
    """Запускает мастер создания с полями из прошлого мероприятия (дата — новая)."""
    categories = [
        item.strip()
        for item in str(source_event.get("category") or "").split(",")
        if item.strip()
    ]
    price_total = source_event.get("price_total") or 0
    price_per_person = source_event.get("price_per_person") or 0
    if price_total and float(price_total) > 0:
        price_mode = "total"
    elif price_per_person and float(price_per_person) > 0:
        price_mode = "per_person"
    else:
        price_mode = "free"

    period_end = source_event.get("period_end")
    await state.update_data(
        title=source_event.get("title", ""),
        description=source_event.get("description"),
        duration_minutes=source_event.get("duration_minutes"),
        location=source_event.get("location"),
        price_mode=price_mode,
        price_total=price_total if price_mode == "total" else None,
        price_per_person=price_per_person if price_mode == "per_person" else None,
        participant_limit=source_event.get("participant_limit"),
        carpool_enabled=bool(source_event.get("carpool_enabled")),
        selected_categories=categories,
        period_mode="range" if period_end else "none",
        period_end=period_end,
        from_copy=True,
        copy_source_id=source_event.get("id"),
    )
    await _prompt_datetime_step(
        message,
        state,
        prefix="📋 Шаблон загружен из прошлого мероприятия.",
    )


async def _prompt_datetime_step(message: Message, state: FSMContext, *, prefix: str = "", hint: str = "") -> None:
    await state.set_state(CreateEvent.datetime)
    body = _datetime_example_text()
    if hint:
        body = f"{body}\n{hint}"
    if prefix:
        body = f"{prefix}\n{body}"
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.datetime.state, body),
        reply_markup=event_datetime_keyboard(back_callback="event_back"),
        parse_mode="HTML",
    )


@router.message(Command("create_event"))
@registered_user_only
async def cmd_create_event(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("❌ Команду /create_event нужно запускать в личных сообщениях с ботом.")
        return

    await start_create_event_wizard(message, state)


async def _show_event_step_prompt(message: Message, state: FSMContext, state_name: str) -> None:
    data = await state.get_data()
    if state_name == CreateEvent.title.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.title.state, wizard_prompt("title")), reply_markup=cancel_keyboard())
    elif state_name == CreateEvent.description.state:
        data = await state.get_data()
        if data.get("from_template"):
            await _prompt_template_description(message, state)
        else:
            await answer_private_intermediate(
                message,
                state,
                event_step_prompt(CreateEvent.description.state, wizard_prompt("description")),
                reply_markup=skip_field_keyboard("description", back_callback="event_back"),
            )
    elif state_name == CreateEvent.datetime.state:
        await answer_private_intermediate(
            message,
            state,
            event_step_prompt(CreateEvent.datetime.state, _datetime_example_text()),
            reply_markup=event_datetime_keyboard(back_callback="event_back"),
            parse_mode="HTML",
        )
    elif state_name == CreateEvent.period_mode.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.period_mode.state, wizard_prompt("period_mode")), reply_markup=event_period_mode_keyboard(back_callback="event_back"))
    elif state_name == CreateEvent.period_end.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.period_end.state, wizard_prompt("period_end")), reply_markup=cancel_keyboard(back_callback="event_back"))
    elif state_name == CreateEvent.duration.state:
        prompt = event_step_prompt(
            CreateEvent.duration.state,
            wizard_prompt("duration")
            if data.get("period_end")
            else f"{wizard_prompt('duration')}\nПример: 2.5",
        )
        await answer_private_intermediate(message, state, prompt, reply_markup=skip_field_keyboard("duration", back_callback="event_back"))
    elif state_name == CreateEvent.location.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.location.state, wizard_prompt("location")), reply_markup=skip_field_keyboard("location", back_callback="event_back"))
    elif state_name == CreateEvent.price_mode.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.price_mode.state, wizard_prompt("price_mode")), reply_markup=event_price_mode_keyboard(back_callback="event_back"))
    elif state_name == CreateEvent.price.state:
        mode = data.get("price_mode")
        prompt = event_step_prompt(
            CreateEvent.price_mode.state,
            wizard_prompt("price_total")
            if mode == "total"
            else wizard_prompt("price_person"),
        )
        await answer_private_intermediate(message, state, prompt, reply_markup=cancel_keyboard(back_callback="event_back"))
    elif state_name == CreateEvent.limit.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.limit.state, wizard_prompt("limit")), reply_markup=skip_field_keyboard("limit", back_callback="event_back"))
    elif state_name == CreateEvent.carpool.state:
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.carpool.state, CARPOOL_HELP_TEXT), reply_markup=carpool_keyboard(back_callback="event_back"), parse_mode="HTML")
    elif state_name == CreateEvent.thread.state:
        topics = await get_topics_list_from_db()
        if topics:
            await answer_private_intermediate(
                message,
                state,
                event_step_prompt(CreateEvent.thread.state, "🗂 Выберите, где опубликовать мероприятие:"),
                reply_markup=choose_topic_keyboard(topics, back_callback="event_back"),
            )
        else:
            await state.update_data(thread_id=None)
            await state.set_state(CreateEvent.category)
            await answer_private_intermediate(
                message,
                state,
                event_step_prompt(
                    CreateEvent.category.state,
                    "⚠️ Тем не найдено. Опубликуем в основной чат.\n"
                    "💡 Отправьте сообщение в любую тему группы, и бот её автоматически обнаружит.\n\n"
                    "📂 Выберите группу категории:",
                ),
                reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
            )
    elif state_name == CreateEvent.category.state:
        await state.update_data(active_category_group=None)
        await answer_private_intermediate(
            message,
            state,
            event_step_prompt(CreateEvent.category.state, wizard_prompt("category_group")),
            reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
        )
    elif state_name == CreateEvent.preview.state:
        await _show_preview_step(message, state)


async def _prompt_template_title(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    suggested = data.get("template_suggested_title", "")
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.title.state,
            f"⚡ Шаблон предлагает название:\n<b>{suggested}</b>\n\nОставить или ввести своё?",
        ),
        reply_markup=template_field_keyboard("event_tpl_title_keep", "event_tpl_title_custom"),
        parse_mode="HTML",
    )


async def _prompt_template_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    suggested = data.get("template_suggested_description", "")
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.description.state,
            f"⚡ Шаблон предлагает описание:\n<i>{suggested}</i>\n\nОставить, пропустить или ввести своё?",
        ),
        reply_markup=template_field_keyboard(
            "event_tpl_desc_keep",
            "event_tpl_desc_custom",
            skip_callback="event_tpl_desc_skip",
            back_callback="event_back",
        ),
        parse_mode="HTML",
    )


async def _go_to_datetime_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    hint = (
        "📌 Для этого формата на следующем шаге удобно выбрать период действия."
        if data.get("template_period_hint")
        else ""
    )
    await _prompt_datetime_step(message, state, hint=hint)


async def _show_preview_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    selected_categories = dedupe_categories(data.get("selected_categories", []))
    if not selected_categories:
        await state.set_state(CreateEvent.category)
        await answer_private_intermediate(
            message,
            state,
            event_step_prompt(CreateEvent.category.state, wizard_prompt("category_group")),
            reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
        )
        return

    category_value = ",".join(selected_categories)
    user_id = getattr(getattr(message, "from_user", None), "id", None) or data.get("creator_id", 0)
    event_data = await build_event_payload(state, category_value, user_id)
    organizer_mention = await get_user_mention(user_id, message.bot)
    responsible_id = event_data.get("responsible_id", user_id)
    responsible_mention = await get_user_mention(responsible_id, message.bot)
    from bot.database import get_topic_name_by_thread_id

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


@router.callback_query(F.data == "event_back")
async def event_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    data = await state.get_data()
    previous_map = {
        CreateEvent.description.state: CreateEvent.title.state,
        CreateEvent.datetime.state: CreateEvent.description.state,
        CreateEvent.period_mode.state: CreateEvent.datetime.state,
        CreateEvent.period_end.state: CreateEvent.period_mode.state,
        CreateEvent.duration.state: CreateEvent.period_mode.state,
        CreateEvent.location.state: CreateEvent.duration.state,
        CreateEvent.price_mode.state: CreateEvent.location.state,
        CreateEvent.price.state: CreateEvent.price_mode.state,
        CreateEvent.limit.state: CreateEvent.price_mode.state,
        CreateEvent.carpool.state: CreateEvent.limit.state,
        CreateEvent.thread.state: CreateEvent.carpool.state,
        CreateEvent.preview.state: CreateEvent.category.state,
    }
    if current == CreateEvent.category.state:
        previous = CreateEvent.thread.state if data.get("thread_step_shown") else CreateEvent.carpool.state
    else:
        previous = previous_map.get(current)
    if not previous:
        await finalize_callback(callback, "Вы уже на первом шаге", show_alert=True)
        return
    await state.set_state(previous)
    if previous == CreateEvent.title.state and data.get("from_template"):
        await _prompt_template_title(callback.message, state)
    else:
        await _show_event_step_prompt(callback.message, state, previous)
    await finalize_callback(callback, "Шаг назад", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


EVENT_TEMPLATES = {
    "sport": {
        "title": "Спортивная встреча",
        "description": "Собираемся на активность: тренировка, командная игра или прогулка в бодром темпе. Подходит для любого уровня подготовки.",
        "selected_categories": ["спорт"],
    },
    "language": {
        "title": "Языковой клуб",
        "description": "Практикуем разговорный язык в дружеском формате: темы, мини-игры, обмен словами и поддержка без экзаменационного стресса.",
        "selected_categories": ["обучение", "общение"],
        "period_hint": True,
    },
    "food": {
        "title": "Гастровстреча",
        "description": "Встречаемся за едой: кафе, пикник, дегустация или совместная готовка. Формат для общения и новых знакомств.",
        "selected_categories": ["еда", "общение"],
    },
    "movie": {
        "title": "Киновечер",
        "description": "Смотрим фильм или подборку видео, обсуждаем впечатления и делимся рекомендациями.",
        "selected_categories": ["киновечер"],
    },
    "astronomy": {
        "title": "Астрономическая встреча",
        "description": "Наблюдаем небо, обсуждаем космос, телескопы и интересные астрономические события.",
        "selected_categories": ["астрономия", "обучение"],
    },
    "lecture": {
        "title": "Мини-лекция",
        "description": "Один или несколько участников делятся темой, опытом или разбором. После — вопросы и свободное обсуждение.",
        "selected_categories": ["обучение", "саморазвитие"],
    },
    "karting": {
        "title": "Картинг",
        "description": "Организуем заезды на картинге: бронирование, сбор участников, мини-турнир и фото после финиша.",
        "selected_categories": ["картинг"],
    },
    "pc_coop": {
        "title": "Кооперативная игра на ПК",
        "description": "Собираем команду для кооперативной игры на ПК: выбираем игру, голосовой чат и удобное время для всех.",
        "selected_categories": ["ПК игры"],
    },    
    "book": {
        "title": "Книжный клуб",
        "description": "Читаем выбранную книгу, делимся мыслями и встречаемся на обсуждение.",
        "selected_categories": ["книжный клуб"],
        "period_hint": True,
    },
    "quiz": {
        "title": "Квиз",
        "description": "Командная интеллектуальная игра: вопросы, азарт и ламповое общение.",
        "selected_categories": ["викторины"],
    },
    "boardgames": {
        "title": "Настолки",
        "description": "Играем в настольные игры. Можно прийти со своей игрой или присоединиться к столу.",
        "selected_categories": ["настолки"],
    },
    "walk": {
        "title": "Прогулка",
        "description": "Неспешная прогулка, живое общение и новые знакомства.",
        "selected_categories": ["прогулки", "живое общение"],
    },
}


@router.callback_query(F.data.startswith("template_event_"))
@registered_user_only
async def quick_event_template(callback: CallbackQuery, state: FSMContext):
    if callback.message.chat.type != "private":
        await finalize_callback(callback, "Шаблоны доступны в личных сообщениях", show_alert=True)
        return

    template_key = callback.data.removeprefix("template_event_")
    template = EVENT_TEMPLATES.get(template_key)
    if not template:
        await finalize_callback(callback, "Шаблон недоступен", show_alert=True)
        return

    await state.set_state(CreateEvent.title)
    await state.update_data(
        template_suggested_title=template["title"],
        template_suggested_description=template["description"],
        selected_categories=dedupe_categories(list(template["selected_categories"])),
        active_category_group=None,
        from_template=True,
        template_period_hint=bool(template.get("period_hint")),
        awaiting_custom_title=False,
        awaiting_custom_description=False,
    )
    await _prompt_template_title(callback.message, state)
    await finalize_callback(callback, "Шаблон применён", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.title, F.data == "event_tpl_title_keep")
async def template_title_keep(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(title=data.get("template_suggested_title", ""), awaiting_custom_title=False)
    await state.set_state(CreateEvent.description)
    await _prompt_template_description(callback.message, state)
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.title, F.data == "event_tpl_title_custom")
async def template_title_custom(callback: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_custom_title=True)
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(CreateEvent.title.state, "✏️ Введите своё название мероприятия:"),
        reply_markup=cancel_keyboard(back_callback="event_back"),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.description, F.data == "event_tpl_desc_keep")
async def template_desc_keep(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(description=data.get("template_suggested_description", ""))
    await _go_to_datetime_step(callback.message, state)
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.description, F.data == "event_tpl_desc_skip")
async def template_desc_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description="")
    await _go_to_datetime_step(callback.message, state)
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.description, F.data == "event_tpl_desc_custom")
async def template_desc_custom(callback: CallbackQuery, state: FSMContext):
    await state.update_data(awaiting_custom_description=True)
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(CreateEvent.description.state, "✏️ Введите своё описание (или «пропустить»):"),
        reply_markup=skip_field_keyboard("description", back_callback="event_back"),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.title, ~F.text.startswith("/"))
async def process_title(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(title=message.text, awaiting_custom_title=False)
    await state.set_state(CreateEvent.description)
    if data.get("from_template"):
        await _prompt_template_description(message, state)
        return
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.description.state, wizard_prompt("description")),
        reply_markup=skip_field_keyboard("description", back_callback="event_back"),
    )


@router.callback_query(CreateEvent.description, F.data == "skip_description")
async def skip_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description="")
    await _prompt_datetime_step(callback.message, state)
    await finalize_callback(callback, "Описание пропущено", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.description, ~F.text.startswith("/"))
async def process_description(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(
        description=message.text if message.text.lower() != "пропустить" else "",
        awaiting_custom_description=False,
    )
    if data.get("from_template"):
        await _go_to_datetime_step(message, state)
        return
    await _prompt_datetime_step(message, state)


@router.callback_query(
    CreateEvent.datetime,
    F.data.in_({"event_dt_tonight", "event_dt_tomorrow", "event_dt_saturday"}),
)
async def quick_datetime(callback: CallbackQuery, state: FSMContext):
    dt = _quick_datetime(callback.data)
    if dt <= datetime.now(TZ):
        await finalize_callback(callback, "Выберите другую дату", show_alert=True)
        return
    await _advance_after_datetime(callback.message, state, dt)
    await finalize_callback(callback, f"📅 {dt.strftime('%d.%m.%Y %H:%M')}", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.datetime, ~F.text.startswith("/"))
async def process_datetime(message: Message, state: FSMContext):
    dt = await parse_datetime(message.text)
    if not dt:
        await answer_private_intermediate(
            message,
            state,
            "❌ Неверный формат или дата в прошлом.\n"
            "Используйте: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Примеры: 25.05.2026 19:30, 01.06.2026 10:00",
            reply_markup=event_datetime_keyboard(back_callback="event_back"),
        )
        return

    await _advance_after_datetime(message, state, dt)


@router.callback_query(CreateEvent.period_mode, F.data.startswith("event_period_"))
async def process_period_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.removeprefix("event_period_")
    if mode == "none":
        await state.update_data(period_end=None)
        await state.set_state(CreateEvent.duration)
        await answer_private_intermediate(
            callback.message,
            state,
            event_step_prompt(
                CreateEvent.duration.state,
                f"{wizard_prompt('duration')}\nПример: 2.5",
            ),
            reply_markup=skip_field_keyboard("duration", back_callback="event_back"),
        )
        await finalize_callback(callback, "Разовое мероприятие", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    if mode == "range":
        await state.set_state(CreateEvent.period_end)
        await answer_private_intermediate(
            callback.message,
            state,
            event_step_prompt(
                CreateEvent.period_mode.state,
                f"{wizard_prompt('period_end')}\nПример: 30.06.2026 23:59",
            ),
            reply_markup=cancel_keyboard(back_callback="event_back"),
        )
        await finalize_callback(callback, "Период действия", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    await finalize_callback(callback, "Некорректный выбор", show_alert=True)


@router.message(CreateEvent.period_end, ~F.text.startswith("/"))
async def process_period_end(message: Message, state: FSMContext):
    end_dt = await parse_datetime(message.text)
    data = await state.get_data()
    start_dt = datetime.fromisoformat(data["date_time"])
    if not end_dt or end_dt <= start_dt:
        await answer_private_intermediate(
            message,
            state,
            "❌ Дата окончания должна быть позже даты старта.\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ",
        )
        return

    await state.update_data(period_end=end_dt.isoformat())
    await state.set_state(CreateEvent.duration)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.duration.state,
            f"{wizard_prompt('duration')}\n"
            "Для книжного клуба можно пропустить — период уже сохранён.",
        ),
        reply_markup=skip_field_keyboard("duration", back_callback="event_back"),
    )


@router.callback_query(CreateEvent.duration, F.data == "skip_duration")
async def skip_duration(callback: CallbackQuery, state: FSMContext):
    await state.update_data(duration_minutes=None)
    await state.set_state(CreateEvent.location)
    await answer_private_intermediate(callback.message, state, event_step_prompt(CreateEvent.location.state, wizard_prompt("location")), reply_markup=skip_field_keyboard("location", back_callback="event_back"))
    await finalize_callback(callback, "Длительность пропущена", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.duration, ~F.text.startswith("/"))
async def process_duration(message: Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        duration_minutes = None
    else:
        try:
            duration_minutes = int(float(message.text) * 60)
        except ValueError:
            await answer_private_intermediate(message, state, err("Неверный формат.\nПример: 2 или 2.5\nИли напишите: пропустить"))
            return

    await state.update_data(duration_minutes=duration_minutes)
    await state.set_state(CreateEvent.location)
    await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.location.state, wizard_prompt("location")), reply_markup=skip_field_keyboard("location", back_callback="event_back"))


async def _ask_price_mode(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEvent.price_mode)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.price_mode.state, wizard_prompt("price_mode")),
        reply_markup=event_price_mode_keyboard(back_callback="event_back"),
    )


@router.callback_query(CreateEvent.location, F.data == "skip_location")
async def skip_location(callback: CallbackQuery, state: FSMContext):
    await state.update_data(location=None)
    await _ask_price_mode(callback.message, state)
    await finalize_callback(callback, "Место пропущено", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.location, ~F.text.startswith("/"))
async def process_location(message: Message, state: FSMContext):
    if message.text.lower() == "пропустить":
        await state.update_data(location=None)
    else:
        await state.update_data(location=message.text)
    await _ask_price_mode(message, state)


@router.callback_query(CreateEvent.price_mode, F.data.startswith("price_mode_"))
async def process_price_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.removeprefix("price_mode_")
    await state.update_data(price_mode=mode)
    if mode == "free":
        await state.update_data(price_total=None, price_per_person=None)
        await state.set_state(CreateEvent.limit)
        await answer_private_intermediate(
            callback.message,
            state,
            event_step_prompt(CreateEvent.limit.state, wizard_prompt("limit")),
            reply_markup=skip_field_keyboard("limit", back_callback="event_back"),
        )
        await finalize_callback(callback, "Бесплатно", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    await state.set_state(CreateEvent.price)
    if mode == "total":
        prompt = event_step_prompt(CreateEvent.price_mode.state, wizard_prompt("price_total"))
    else:
        prompt = event_step_prompt(CreateEvent.price_mode.state, wizard_prompt("price_person"))
    await answer_private_intermediate(callback.message, state, prompt, reply_markup=cancel_keyboard(back_callback="event_back"))
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.price, ~F.text.startswith("/"))
async def process_price(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("price_mode")
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await answer_private_intermediate(message, state, err("Неверный формат.\nВведите число, пример: 500"))
        return
    if amount < 0:
        await answer_private_intermediate(message, state, "❌ Сумма не может быть отрицательной.")
        return

    total = amount if mode == "total" else None
    per_person = amount if mode == "person" else None

    await state.update_data(price_total=total, price_per_person=per_person)
    await state.set_state(CreateEvent.limit)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.limit.state, wizard_prompt("limit")),
        reply_markup=skip_field_keyboard("limit", back_callback="event_back"),
    )


@router.callback_query(CreateEvent.limit, F.data == "skip_limit")
async def skip_limit(callback: CallbackQuery, state: FSMContext):
    await state.update_data(participant_limit=None)
    await state.set_state(CreateEvent.carpool)
    await answer_private_intermediate(callback.message, state, event_step_prompt(CreateEvent.carpool.state, CARPOOL_HELP_TEXT), reply_markup=carpool_keyboard(back_callback="event_back"), parse_mode="HTML")
    await finalize_callback(callback, "Лимит пропущен", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.limit, ~F.text.startswith("/"))
async def process_limit(message: Message, state: FSMContext):
    if message.text.lower() in {"без лимита", "пропустить"}:
        participant_limit = None
    else:
        try:
            participant_limit = int(message.text)
        except ValueError:
            await answer_private_intermediate(message, state, "❌ Введите число, 'без лимита' или 'пропустить':")
            return

    await state.update_data(participant_limit=participant_limit)
    await state.set_state(CreateEvent.carpool)
    await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.carpool.state, CARPOOL_HELP_TEXT), reply_markup=carpool_keyboard(back_callback="event_back"), parse_mode="HTML")