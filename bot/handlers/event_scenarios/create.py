from aiogram import F, Router
from datetime import datetime
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.constants import CARPOOL_HELP_TEXT
from bot.filters.registered_user import registered_user_only
from bot.keyboards import cancel_keyboard, skip_field_keyboard, carpool_keyboard, event_period_mode_keyboard, event_price_mode_keyboard
from .shared import CreateEvent, event_step_prompt, parse_datetime
from bot.utils.design import wizard_prompt
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.utils.ui import answer_private_intermediate, err

router = Router(name=__name__)

async def start_create_event_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEvent.title)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.title.state, wizard_prompt("title")),
        reply_markup=cancel_keyboard(),
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
        await answer_private_intermediate(message, state, event_step_prompt(CreateEvent.description.state, wizard_prompt("description")), reply_markup=skip_field_keyboard("description", back_callback="event_back"))
    elif state_name == CreateEvent.datetime.state:
        await answer_private_intermediate(
            message,
            state,
            event_step_prompt(
                CreateEvent.datetime.state,
                f"{wizard_prompt('datetime')}\nПример: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            ),
            reply_markup=cancel_keyboard(back_callback="event_back"),
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


@router.callback_query(F.data == "event_back")
async def event_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    previous = {
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
        CreateEvent.category.state: CreateEvent.thread.state,
        CreateEvent.preview.state: CreateEvent.category.state,
    }.get(current)
    if not previous:
        await finalize_callback(callback, "Вы уже на первом шаге", show_alert=True)
        return
    await state.set_state(previous)
    await _show_event_step_prompt(callback.message, state, previous)
    await finalize_callback(callback, "Шаг назад", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


EVENT_TEMPLATES = {
    "sport": {
        "title": "Спортивная встреча",
        "description": "Собираемся на активность: тренировка, командная игра или прогулка в бодром темпе. Подходит для любого уровня подготовки.",
        "selected_categories": ["спорт", "активный отдых"],
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
        "selected_categories": ["еда", "гастрономия", "общение"],
    },
    "movie": {
        "title": "Киновечер",
        "description": "Смотрим фильм или подборку видео, обсуждаем впечатления и делимся рекомендациями.",
        "selected_categories": ["кино", "киновечер"],
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
        "selected_categories": ["картинг", "активный отдых", "автоспорт"],
    },
    "pc_coop": {
        "title": "Кооперативная игра на ПК",
        "description": "Собираем команду для кооперативной игры на ПК: выбираем игру, голосовой чат и удобное время для всех.",
        "selected_categories": ["ПК игры", "игры"],
    },    
    "book": {
        "title": "Книжный клуб",
        "description": "Читаем выбранную книгу, делимся мыслями и встречаемся на обсуждение.",
        "selected_categories": ["книжный клуб", "обсуждение книг"],
        "period_hint": True,
    },
    "quiz": {
        "title": "Квиз",
        "description": "Командная интеллектуальная игра: вопросы, азарт и ламповое общение.",
        "selected_categories": ["викторины", "интеллектуальные игры"],
    },
    "boardgames": {
        "title": "Настолки",
        "description": "Играем в настольные игры. Можно прийти со своей игрой или присоединиться к столу.",
        "selected_categories": ["настолки", "игры"],
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

    await state.set_state(CreateEvent.datetime)
    await state.update_data(
        title=template["title"],
        description=template["description"],
        selected_categories=list(template["selected_categories"]),
        active_category_group=None,
    )
    hint = "\n📌 Для этого формата на следующем шаге удобно выбрать период действия." if template.get("period_hint") else ""
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(
            CreateEvent.datetime.state,
            f"⚡ Шаблон «{template['title']}» применён.\n"
            f"Категории и описание уже подставлены.{hint}\n\n"
            f"🗓 {wizard_prompt('datetime')}",
        ),
        reply_markup=cancel_keyboard(),
    )
    await finalize_callback(callback, "Шаблон применён", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.title, ~F.text.startswith("/"))
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(CreateEvent.description)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.description.state, wizard_prompt("description")),
        reply_markup=skip_field_keyboard("description", back_callback="event_back"),
    )


@router.callback_query(CreateEvent.description, F.data == "skip_description")
async def skip_description(callback: CallbackQuery, state: FSMContext):
    await state.update_data(description="")
    await state.set_state(CreateEvent.datetime)
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(
            CreateEvent.datetime.state,
            f"{wizard_prompt('datetime')}\nПример: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ),
        reply_markup=cancel_keyboard(back_callback="event_back"),
    )
    await finalize_callback(callback, "Описание пропущено", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(CreateEvent.description, ~F.text.startswith("/"))
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text if message.text.lower() != "пропустить" else "")
    await state.set_state(CreateEvent.datetime)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.datetime.state,
            f"{wizard_prompt('datetime')}\nПример: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ),
        reply_markup=cancel_keyboard(back_callback="event_back"),
    )


@router.message(CreateEvent.datetime, ~F.text.startswith("/"))
async def process_datetime(message: Message, state: FSMContext):
    dt = await parse_datetime(message.text)
    if not dt:
        await answer_private_intermediate(
            message,
            state,
            "❌ Неверный формат или дата в прошлом.\n"
            "Используйте: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Примеры: 25.05.2026 19:30, 01.06.2026 10:00"
        )
        return

    await state.update_data(date_time=dt.isoformat(), period_end=None)
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