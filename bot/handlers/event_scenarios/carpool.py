import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.constants import EVENT_CATEGORY_GROUPS
from bot.keyboards import (
    carpool_keyboard,
    category_groups_keyboard,
    choose_topic_keyboard,
    event_responsible_keyboard,
)
from bot.utils.topics import get_topics_list_from_db
from bot.utils.callbacks import finalize_callback
from bot.utils.ui import answer_private_intermediate
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from .shared import CreateEvent, event_step_prompt, show_event_preview

logger = logging.getLogger(__name__)
router = Router(name=__name__)


@router.message(CreateEvent.carpool)
async def process_carpool(message: Message, state: FSMContext):
    if not message.text:
        await answer_private_intermediate(message, state, "Выберите вариант кнопкой ниже.", reply_markup=carpool_keyboard(back_callback="event_back"))
        return

    normalized = message.text.lower().strip()
    if normalized not in {"да", "нет", "yes", "no", "y", "n", "1", "0", "true", "false"}:
        await answer_private_intermediate(message, state, "Нажмите одну из кнопок: «Да» или «Нет».", reply_markup=carpool_keyboard(back_callback="event_back"))
        return

    carpool = normalized in {"да", "yes", "y", "1", "true"}
    await process_carpool_choice(message, state, carpool)


@router.callback_query(CreateEvent.carpool, F.data.in_(["carpool_yes", "carpool_no"]))
async def process_carpool_callback(callback: CallbackQuery, state: FSMContext):
    carpool = callback.data == "carpool_yes"
    await process_carpool_choice(callback.message, state, carpool)
    await finalize_callback(callback, "Выбор сохранён", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


async def process_carpool_choice(message: Message, state: FSMContext, carpool: bool):
    await state.update_data(carpool_enabled=carpool)
    await _prompt_responsible_step(message, state)


async def _prompt_responsible_step(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEvent.responsible)
    await answer_private_intermediate(
        message,
        state,
        event_step_prompt(
            CreateEvent.responsible.state,
            "🧩 Кто будет ответственным за мероприятие?\n"
            "Ответственный помогает с организацией и отображается на карточке, "
            "если это не создатель.",
        ),
        reply_markup=event_responsible_keyboard(back_callback="event_back"),
    )


async def advance_after_responsible(
    message: Message,
    state: FSMContext,
    responsible_id: int,
    user_id: int,
) -> None:
    await state.update_data(responsible_id=responsible_id, awaiting_responsible_input=False)

    topics = await get_topics_list_from_db()
    data = await state.get_data()

    if topics:
        await state.update_data(thread_step_shown=True)
        await state.set_state(CreateEvent.thread)
        prompt = (
            "🗂 Выберите, где опубликовать копию мероприятия:"
            if data.get("from_copy")
            else "🗂 Выберите, где опубликовать мероприятие:"
        )
        await answer_private_intermediate(
            message,
            state,
            event_step_prompt(CreateEvent.thread.state, prompt),
            reply_markup=choose_topic_keyboard(topics, back_callback="event_back"),
        )
        return

    await state.update_data(thread_id=None, thread_step_shown=False)
    if data.get("from_copy") and data.get("selected_categories"):
        await show_event_preview(message, state, user_id, message.bot)
        return

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


@router.callback_query(CreateEvent.thread, F.data.startswith("topic_"))
async def process_topic(callback: CallbackQuery, state: FSMContext):
    try:
        thread_id_str = callback.data.split("_")[1]
        thread_id = int(thread_id_str) if thread_id_str != "0" else None

        await state.update_data(thread_id=thread_id, thread_step_shown=True)

        data = await state.get_data()
        if data.get("from_copy") and data.get("selected_categories"):
            await show_event_preview(callback.message, state, callback.from_user.id, callback.bot)
            await finalize_callback(callback, "✅ Тема выбрана!", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
            return

        await state.set_state(CreateEvent.category)
        await answer_private_intermediate(
            callback.message,
            state,
            event_step_prompt(CreateEvent.category.state, "📂 Выберите группу категории:"),
            reply_markup=category_groups_keyboard(EVENT_CATEGORY_GROUPS, back_callback="event_back"),
        )
        await finalize_callback(callback, "✅ Тема выбрана!", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
    except Exception as exc:
        logger.error(f"Ошибка при обработке темы: {exc}")
        await finalize_callback(callback, "❌ Ошибка! Попробуйте снова.", show_alert=True)
