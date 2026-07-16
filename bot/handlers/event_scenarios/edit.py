import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.constants import EVENT_CATEGORY_GROUPS, EVENT_CATEGORIES, category_badge_key, dedupe_categories
from bot.database import get_event, update_event
from bot.handlers.participation import update_event_message
from bot.keyboards import (
    category_groups_keyboard,
    category_subgroups_keyboard,
    edit_event_carpool_keyboard,
    edit_event_fields_keyboard,
    edit_event_price_mode_keyboard,
    duration_unit_keyboard,
)
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.utils.helpers import parse_int_arg
from bot.utils.ui import answer_private_intermediate
from bot.utils.duration import parse_duration_text, apply_duration_unit
from .shared import parse_datetime, normalize_event_link

logger = logging.getLogger(__name__)
router = Router(name=__name__)


class EditEvent(StatesGroup):
    value = State()
    category = State()


async def _can_edit_event(event_id: int, user_id: int) -> tuple[bool, dict | None]:
    event = await get_event(event_id)
    if not event:
        return False, None
    from bot.utils.roles import is_admin_or_owner

    if user_id == event["creator_id"] or user_id == (event.get("responsible_id") or 0) or is_admin_or_owner(user_id):
        return True, event
    return False, event


async def _refresh_event_card(bot, event: dict) -> None:
    if event.get("message_id"):
        await update_event_message(bot, int(event["id"]), event.get("thread_id") or 0, int(event["message_id"]))


async def _show_edit_menu(message: Message, state: FSMContext, event_id: int, note: str = "") -> None:
    prefix = note + "\n\n" if note else ""
    await answer_private_intermediate(
        message,
        state,
        f"{prefix}✏️ Выберите поле для редактирования (ID <code>{event_id}</code>):",
        reply_markup=edit_event_fields_keyboard(event_id),
        parse_mode="HTML",
    )


async def _start_edit_field(message: Message, state: FSMContext, event_id: int, field: str, prompt: str) -> None:
    await state.set_state(EditEvent.value)
    await state.update_data(edit_event_id=event_id, edit_field=field, edit_price_mode=None)
    await answer_private_intermediate(message, state, prompt)


@router.message(Command("edit_event"))
async def cmd_edit_event(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("❌ Команду /edit_event нужно запускать в личных сообщениях с ботом.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /edit_event <event_id>")
        return

    event_id = parse_int_arg(parts[1])
    if event_id is None:
        await message.answer("❌ event_id должен быть числом.")
        return

    allowed, event = await _can_edit_event(event_id, message.from_user.id)
    if not event:
        await message.answer("❌ Мероприятие не найдено.")
        return
    if not allowed:
        await message.answer("❌ Редактировать может создатель, ответственный или админ.")
        return

    await state.update_data(edit_event_id=event_id, edit_selected_categories=[])
    await _show_edit_menu(message, state, event_id)


@router.callback_query(F.data.startswith("edit_menu_"))
async def edit_back_to_menu(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.removeprefix("edit_menu_"))
    allowed, _ = await _can_edit_event(event_id, callback.from_user.id)
    if not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return
    await state.set_state(None)
    await _show_edit_menu(callback.message, state, event_id)
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data.startswith("edit_done_"))
async def edit_done(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await finalize_callback(callback, "Редактирование завершено")
    await callback.message.answer("✅ Изменения сохранены. Карточка в группе обновлена.")


@router.callback_query(F.data.startswith("edit_field_"))
async def edit_pick_field(callback: CallbackQuery, state: FSMContext):
    _, _, event_raw, field = callback.data.split("_", 3)
    event_id = int(event_raw)
    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return

    prompts = {
        "title": "📝 Введите новое название:",
        "description": "📄 Введите новое описание (или «-» чтобы очистить):",
        "datetime": "🗓 Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):",
        "period_end": "📆 Введите дату окончания периода (ДД.ММ.ГГГГ ЧЧ:ММ) или «-» чтобы убрать:",
        "duration": (
            "⏱ Введите длительность.\n"
            "Примеры: 1 ч 30 мин, 90 мин, 2\n"
            "Или «-» чтобы убрать:"
        ),
        "location": "📍 Введите новое место или «-» чтобы убрать:",
        "link": "🔗 Введите ссылку или «-» чтобы убрать:",
        "limit": "👥 Введите лимит участников, «без лимита» или «-»:",
    }

    if field == "price":
        await answer_private_intermediate(
            callback.message,
            state,
            "💰 Выберите тип стоимости:",
            reply_markup=edit_event_price_mode_keyboard(event_id),
        )
        await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    if field == "carpool":
        await answer_private_intermediate(
            callback.message,
            state,
            "🚗 Включить карпулинг?",
            reply_markup=edit_event_carpool_keyboard(event_id),
        )
        await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    if field == "category":
        existing = [item.strip() for item in (event.get("category") or "").split(",") if item.strip()]
        await state.set_state(EditEvent.category)
        await state.update_data(
            edit_event_id=event_id,
            edit_selected_categories=dedupe_categories(existing),
            edit_active_category_group=None,
        )
        await answer_private_intermediate(
            callback.message,
            state,
            "📂 Выберите группу категории:",
            reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback=f"edit_menu_{event_id}"),
        )
        await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    prompt = prompts.get(field)
    if not prompt:
        await finalize_callback(callback, "Поле недоступно", show_alert=True)
        return

    await _start_edit_field(callback.message, state, event_id, field, prompt)
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_mode(callback: CallbackQuery, state: FSMContext):
    _, _, event_raw, mode = callback.data.split("_", 3)
    event_id = int(event_raw)
    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return

    if mode == "free":
        await update_event(event_id, {"price_total": 0.0, "price_per_person": 0.0})
        updated = await get_event(event_id)
        await _refresh_event_card(callback.bot, updated)
        await state.set_state(None)
        await _show_edit_menu(callback.message, state, event_id, "✅ Стоимость: бесплатно")
        await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return

    await state.set_state(EditEvent.value)
    await state.update_data(edit_event_id=event_id, edit_field="price", edit_price_mode=mode)
    label = "общую сумму" if mode == "total" else "стоимость с человека"
    await answer_private_intermediate(callback.message, state, f"💰 Введите {label} (число):")
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(F.data.startswith("edit_carpool_"))
async def edit_carpool_choice(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    event_id = int(parts[2])
    enabled = parts[3] == "yes"
    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return

    await update_event(event_id, {"carpool_enabled": enabled})
    updated = await get_event(event_id)
    await _refresh_event_card(callback.bot, updated)
    await state.set_state(None)
    await _show_edit_menu(
        callback.message,
        state,
        event_id,
        f"✅ Карпулинг: {'включён' if enabled else 'выключен'}",
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(EditEvent.value, ~F.text.startswith("/"))
async def edit_apply_value(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = int(data["edit_event_id"])
    field = data["edit_field"]
    allowed, event = await _can_edit_event(event_id, message.from_user.id)
    if not event or not allowed:
        await message.answer("❌ Нет доступа.")
        await state.clear()
        return

    text = (message.text or "").strip()
    updates: dict = {}

    if field == "title":
        if not text:
            await message.answer("❌ Название не может быть пустым.")
            return
        updates["title"] = text
    elif field == "description":
        updates["description"] = "" if text == "-" else text
    elif field == "datetime":
        dt = await parse_datetime(text)
        if not dt:
            await message.answer("❌ Неверный формат или дата в прошлом.")
            return
        updates["date_time"] = dt.isoformat()
    elif field == "period_end":
        if text == "-":
            updates["period_end"] = ""
        else:
            dt = await parse_datetime(text)
            if not dt:
                await message.answer("❌ Неверный формат даты.")
                return
            updates["period_end"] = dt.isoformat()
    elif field == "duration":
        if text == "-":
            updates["duration_minutes"] = 0
        else:
            parsed = parse_duration_text(text)
            if parsed.error:
                await message.answer(
                    "❌ Неверный формат.\nПримеры: 1 ч 30 мин, 90 мин, 2\nИли «-»"
                )
                return
            if parsed.needs_unit:
                await state.update_data(
                    edit_field="duration",
                    pending_duration_value=parsed.raw_value,
                )
                await message.answer(
                    f"⏱ Уточни: <b>{parsed.raw_value:g}</b> — это часы или минуты?",
                    reply_markup=duration_unit_keyboard(cancel=False),
                    parse_mode="HTML",
                )
                return
            updates["duration_minutes"] = parsed.minutes or 0
    elif field == "location":
        updates["location"] = None if text == "-" else text
    elif field == "link":
        if text == "-":
            updates["link"] = ""
        else:
            link = normalize_event_link(text)
            if not link:
                await message.answer("❌ Не похоже на ссылку. Пример: https://example.com")
                return
            updates["link"] = link
    elif field == "limit":
        if text in {"-", "без лимита"}:
            updates["participant_limit"] = 0
        else:
            try:
                updates["participant_limit"] = int(text)
            except ValueError:
                await message.answer("❌ Введите число или «без лимита».")
                return
    elif field == "price":
        mode = data.get("edit_price_mode")
        try:
            amount = float(text.replace(",", "."))
        except ValueError:
            await message.answer("❌ Введите число.")
            return
        if mode == "total":
            updates["price_total"] = amount
            updates["price_per_person"] = 0.0
        else:
            updates["price_per_person"] = amount
            updates["price_total"] = 0.0
    else:
        await message.answer("❌ Неизвестное поле.")
        return

    await update_event(event_id, updates)
    updated = await get_event(event_id)
    await _refresh_event_card(message.bot, updated)
    await state.set_state(None)
    await _show_edit_menu(message, state, event_id, "✅ Поле обновлено")


@router.callback_query(EditEvent.value, F.data.startswith("duration_unit_"))
async def edit_duration_unit(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "duration":
        await finalize_callback(callback, "Сначала выберите длительность", show_alert=True)
        return

    event_id = int(data["edit_event_id"])
    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return

    raw_value = data.get("pending_duration_value")
    unit = callback.data.removeprefix("duration_unit_")
    minutes = apply_duration_unit(float(raw_value), unit) if raw_value is not None else None
    if minutes is None:
        await finalize_callback(callback, "Некорректное значение", show_alert=True)
        return

    await update_event(event_id, {"duration_minutes": minutes})
    updated = await get_event(event_id)
    await _refresh_event_card(callback.bot, updated)
    await state.set_state(None)
    await _show_edit_menu(callback.message, state, event_id, "✅ Длительность обновлена")
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(EditEvent.category, F.data.startswith("category_group_"))
async def edit_open_category_group(callback: CallbackQuery, state: FSMContext):
    group_key = callback.data.replace("category_group_", "", 1)
    if group_key not in EVENT_CATEGORY_GROUPS:
        await finalize_callback(callback, "Группа недоступна", show_alert=True)
        return

    data = await state.get_data()
    event_id = int(data["edit_event_id"])
    selected = data.get("edit_selected_categories", [])
    await state.update_data(edit_active_category_group=group_key)
    await answer_private_intermediate(
        callback.message,
        state,
        f"Выберите подкатегории в группе «{EVENT_CATEGORY_GROUPS[group_key]['title']}»:",
        reply_markup=category_subgroups_keyboard(group_key, EVENT_CATEGORY_GROUPS, selected),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(EditEvent.category, F.data.startswith("category_toggle_"))
async def edit_toggle_category(callback: CallbackQuery, state: FSMContext):
    category_value = callback.data.replace("category_toggle_", "", 1)
    if category_value not in EVENT_CATEGORIES:
        await finalize_callback(callback, "Подкатегория недоступна", show_alert=True)
        return

    data = await state.get_data()
    active_group = data.get("edit_active_category_group")
    if not active_group:
        await finalize_callback(callback, "Сначала выберите группу", show_alert=True)
        return

    selected = dedupe_categories(data.get("edit_selected_categories", []))
    if category_value in selected:
        selected.remove(category_value)
    else:
        badge_key = category_badge_key(category_value)
        selected = [item for item in selected if category_badge_key(item) != badge_key]
        selected.append(category_value)
        selected = dedupe_categories(selected)

    await state.update_data(edit_selected_categories=selected)
    await finalize_callback(callback, "Список обновлён")
    await callback.message.edit_reply_markup(
        reply_markup=category_subgroups_keyboard(active_group, EVENT_CATEGORY_GROUPS, selected)
    )


@router.callback_query(EditEvent.category, F.data == "category_back")
async def edit_category_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = int(data["edit_event_id"])
    await state.update_data(edit_active_category_group=None)
    await answer_private_intermediate(
        callback.message,
        state,
        "📂 Выберите группу категории:",
        reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback=f"edit_menu_{event_id}"),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(EditEvent.category, F.data == "category_done")
async def edit_finish_categories(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = int(data["edit_event_id"])
    selected = dedupe_categories(data.get("edit_selected_categories", []))
    if not selected:
        await finalize_callback(callback, "Выберите хотя бы одну подкатегорию", show_alert=True)
        return

    allowed, event = await _can_edit_event(event_id, callback.from_user.id)
    if not event or not allowed:
        await finalize_callback(callback, "Нет доступа", show_alert=True)
        return

    await update_event(event_id, {"category": ",".join(selected)})
    updated = await get_event(event_id)
    await _refresh_event_card(callback.bot, updated)
    await state.set_state(None)
    await _show_edit_menu(callback.message, state, event_id, "✅ Категории обновлены")
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
