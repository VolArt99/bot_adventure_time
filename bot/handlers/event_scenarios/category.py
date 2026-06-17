from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.constants import EVENT_CATEGORIES, EVENT_CATEGORY_GROUPS
from bot.keyboards import category_groups_keyboard, category_subgroups_keyboard, event_preview_keyboard
from bot.utils.callbacks import finalize_callback
from bot.utils.ui import answer_private_intermediate
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.database import get_topic_name_by_thread_id
from bot.texts import format_event_message
from bot.utils.helpers import get_user_mention
from bot.utils.design import brand_voice, wizard_prompt
from .shared import CreateEvent, build_event_payload, event_step_prompt, finalize_event_creation

router = Router(name=__name__)


@router.message(CreateEvent.category)
async def process_category(message: Message, state: FSMContext):
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(CreateEvent.category.state, "❌ Выбор категорий теперь только через кнопки ниже."),
        reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
    )


@router.callback_query(CreateEvent.category, F.data.startswith("category_group_"))
async def open_category_group(callback: CallbackQuery, state: FSMContext):
    group_key = callback.data.replace("category_group_", "", 1)
    if group_key not in EVENT_CATEGORY_GROUPS:
        await finalize_callback(callback, "Группа недоступна", show_alert=True)
        return

    data = await state.get_data()
    selected_categories = data.get("selected_categories", [])
    await state.update_data(active_category_group=group_key)
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(
            CreateEvent.category.state,
            f"Выберите подкатегории в группе «{EVENT_CATEGORY_GROUPS[group_key]['title']}». "
            f"Можно выбрать несколько.",
        ),
        reply_markup=category_subgroups_keyboard(
            group_key, EVENT_CATEGORY_GROUPS, selected_categories
        ),
    )
    await finalize_callback(callback, "Группа открыта", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.category, F.data.startswith("category_toggle_"))
async def toggle_category(callback: CallbackQuery, state: FSMContext):
    category_value = callback.data.replace("category_toggle_", "", 1)
    if category_value not in EVENT_CATEGORIES:
        await finalize_callback(callback, "Подкатегория недоступна", show_alert=True)
        return

    data = await state.get_data()
    active_group = data.get("active_category_group")
    if not active_group:
        await finalize_callback(callback, "Сначала выберите группу", show_alert=True)
        return

    selected_categories = data.get("selected_categories", [])
    if category_value in selected_categories:
        selected_categories.remove(category_value)
    else:
        selected_categories.append(category_value)

    await state.update_data(selected_categories=selected_categories)
    await finalize_callback(callback, "Список обновлён")
    await callback.message.edit_reply_markup(
        reply_markup=category_subgroups_keyboard(
            active_group, EVENT_CATEGORY_GROUPS, selected_categories
        )
    )


@router.callback_query(CreateEvent.category, F.data == "category_back")
async def back_to_category_groups(callback: CallbackQuery, state: FSMContext):
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(CreateEvent.category.state, wizard_prompt("category_group")),
        reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
    )
    await finalize_callback(callback, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.category, F.data == "category_done")
async def finish_categories(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_categories = data.get("selected_categories", [])
    if not selected_categories:
        await finalize_callback(callback, "Выберите хотя бы одну подкатегорию", show_alert=True)
        return

    category_value = ",".join(selected_categories)
    event_data = await build_event_payload(state, category_value, callback.from_user.id)
    organizer_mention = await get_user_mention(callback.from_user.id, callback.bot)
    responsible_id = event_data.get("responsible_id", callback.from_user.id)
    responsible_mention = await get_user_mention(responsible_id, callback.bot)
    topic_name = await get_topic_name_by_thread_id(event_data.get("thread_id"))
    preview_text = await format_event_message(
        {**event_data, "id": "preview"},
        [],
        [],
        {callback.from_user.id: organizer_mention, responsible_id: responsible_mention},
        topic_name=topic_name,
        organizer_mention=organizer_mention,
        responsible_mention=responsible_mention,
    )
    await state.set_state(CreateEvent.preview)
    await answer_private_intermediate(
        callback.message,
        state,
        event_step_prompt(
            CreateEvent.preview.state,
            f"{brand_voice('event_preview_intro')}\n\n{preview_text}",
        ),
        reply_markup=event_preview_keyboard(),
        parse_mode="HTML",
    )
    await finalize_callback(callback, "Показано превью", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.callback_query(CreateEvent.preview, F.data == "event_preview_publish")
async def publish_previewed_event(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category_value = data.get("category")
    if not category_value:
        await finalize_callback(callback, "Категории не выбраны", show_alert=True)
        return
    
    await finalize_event_creation(
        callback.message,
        state,
        category_value,
        creator_user_id=callback.from_user.id,
    )
    await finalize_callback(callback, brand_voice("event_created"), delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
