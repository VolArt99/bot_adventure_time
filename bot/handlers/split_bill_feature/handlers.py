from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from datetime import datetime
import pytz

from bot.database import is_member_approved
from bot.database import get_approved_member_ids, get_user_events, get_user_id_by_username
from bot.config import TIMEZONE
from bot.keyboards import cancel_keyboard, choose_topic_keyboard
from bot.utils.topics import get_topics_list_from_db
from bot.utils.ui import answer_private_intermediate
from bot.utils.helpers import parse_int_arg
from bot.utils.callbacks import finalize_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE
from bot.filters.approved_member import approved_member_callback_only

from .services import (
    add_split_bill_participant,
    close_bill_if_ready,
    finalize_split_bill,
    get_split_bill,
    get_split_bill_participants,
    mark_split_bill_paid,
    parse_args,
    refresh_split_message,
    refresh_published_split_message,
    remove_split_bill_participant,
    remind_unpaid_participants,
)

router = Router(name=__name__)
TZ = pytz.timezone(TIMEZONE)


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


def _is_private_message(message: Message) -> bool:
    return bool(message and message.chat and message.chat.type == "private")

class SplitBillCreate(StatesGroup):
    title = State()
    amount = State()
    source_event = State()
    target_topic = State()
    transfer_target = State()
    transfer_bank = State()
    transfer_bank_custom = State()
    transfer_recipient_name = State()


SPLIT_BILL_STEP_META = {
    SplitBillCreate.title.state: (1, 7, "🧾 Название"),
    SplitBillCreate.amount.state: (2, 7, "💰 Сумма"),
    SplitBillCreate.source_event.state: (3, 7, "🔗 Мероприятие"),
    SplitBillCreate.target_topic.state: (4, 7, "🗂 Публикация"),
    SplitBillCreate.transfer_target.state: (5, 7, "💸 Реквизиты"),
    SplitBillCreate.transfer_bank.state: (6, 7, "🏦 Банк"),
    SplitBillCreate.transfer_bank_custom.state: (6, 7, "🏦 Банк"),
    SplitBillCreate.transfer_recipient_name.state: (7, 7, "👤 Получатель"),
}


def split_bill_step_prompt(state_name: str, text: str) -> str:
    """Добавляет прогресс мастера split-bill к тексту шага."""
    current, total, label = SPLIT_BILL_STEP_META.get(state_name, (0, 0, ""))
    if not current:
        return text
    return f"Шаг {current}/{total} · {label}\n\n{text}"


async def _show_split_bill_step_prompt(message: Message, state: FSMContext, state_name: str) -> None:
    if state_name == SplitBillCreate.title.state:
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.title.state, "🧾 Введите название чека:"), reply_markup=cancel_keyboard())
    elif state_name == SplitBillCreate.amount.state:
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.amount.state, "💰 Введите общую сумму чека (например, 4200):"), reply_markup=cancel_keyboard(back_callback="sb_back"))
    elif state_name == SplitBillCreate.source_event.state:
        data = await state.get_data()
        upcoming = await get_user_events(int(data.get("creator_id") or 0))
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.source_event.state, "🔗 Укажите ID мероприятия или выберите мероприятие кнопкой ниже."), reply_markup=split_bill_source_event_keyboard(upcoming))
        topics = await get_topics_list_from_db()
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.target_topic.state, "🗂 Выберите подгруппу для публикации разделения чека:"), reply_markup=choose_topic_keyboard(topics, back_callback="sb_back"))
        await ask_transfer_target(message, state)
    elif state_name == SplitBillCreate.transfer_bank.state:
        rows = [
            [InlineKeyboardButton(text="Сбер", callback_data="sb_bank_sber")],
            [InlineKeyboardButton(text="Т-банк", callback_data="sb_bank_tbank")],
            [InlineKeyboardButton(text="Альфа", callback_data="sb_bank_alfa")],
            [InlineKeyboardButton(text="Яндекс", callback_data="sb_bank_yandex")],
            [InlineKeyboardButton(text="Свой вариант", callback_data="sb_bank_other")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="sb_back")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")],
        ]
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_bank.state, "🏦 Выберите банк:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    elif state_name == SplitBillCreate.transfer_bank_custom.state:
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_bank_custom.state, "Введите название банка:"), reply_markup=cancel_keyboard(back_callback="sb_back"))
    elif state_name == SplitBillCreate.transfer_recipient_name.state:
        await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_recipient_name.state, "Введите ФИО получателя перевода:"), reply_markup=cancel_keyboard(back_callback="sb_back"))


@router.callback_query(F.data == "sb_back")
async def split_bill_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    previous = {
        SplitBillCreate.amount.state: SplitBillCreate.title.state,
        SplitBillCreate.source_event.state: SplitBillCreate.amount.state,
        SplitBillCreate.target_topic.state: SplitBillCreate.source_event.state,
        SplitBillCreate.transfer_target.state: SplitBillCreate.target_topic.state,
        SplitBillCreate.transfer_bank.state: SplitBillCreate.transfer_target.state,
        SplitBillCreate.transfer_bank_custom.state: SplitBillCreate.transfer_bank.state,
        SplitBillCreate.transfer_recipient_name.state: SplitBillCreate.transfer_bank.state,
    }.get(current)
    if not previous:
        await finalize_callback(callback, "Вы уже на первом шаге", show_alert=True)
        return
    await state.set_state(previous)
    await _show_split_bill_step_prompt(callback.message, state, previous)
    await finalize_callback(callback, "Шаг назад", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


async def start_split_bill_wizard(message: Message, state: FSMContext, *, creator_id: int) -> None:
    await state.set_state(SplitBillCreate.title)
    await state.update_data(creator_id=creator_id)
    await answer_private_intermediate(
        message,
        state,
        split_bill_step_prompt(SplitBillCreate.title.state, "🧾 Введите название чека:"),
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("split_bill"))
async def cmd_split_bill(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("❌ Команду /split_bill нужно запускать в личных сообщениях с ботом.")
        return

    await start_split_bill_wizard(message, state, creator_id=message.from_user.id)


@router.message(SplitBillCreate.title, ~F.text.startswith("/"))
async def split_bill_title(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(SplitBillCreate.amount)
    await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.amount.state, "💰 Введите общую сумму чека (например, 4200):"), reply_markup=cancel_keyboard(back_callback="sb_back"))


@router.message(SplitBillCreate.amount, ~F.text.startswith("/"))
async def split_bill_amount(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    try:
        amount = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await answer_private_intermediate(message, state, "❌ Сумма должна быть числом, например 4200 или 4200.50")
        return

    if amount <= 0:
        await answer_private_intermediate(message, state, "❌ Сумма должна быть больше 0.")
        return

    await state.update_data(total_amount=amount)
    await state.set_state(SplitBillCreate.source_event)
    upcoming = await get_user_events(message.from_user.id)
    now = datetime.now(TZ)
    upcoming = [
        e for e in upcoming
        if datetime.fromisoformat(e["date_time"]).astimezone(TZ).date() == now.date()
    ]
    keyboard = split_bill_source_event_keyboard(upcoming)
    await answer_private_intermediate(
        message,
        state,
        split_bill_step_prompt(
            SplitBillCreate.source_event.state,
            "🔗 Укажите ID мероприятия, чтобы автоматически подтянуть участников, "
            "или выберите мероприятие кнопкой ниже.",
        ),
        reply_markup=keyboard,
    )


@router.callback_query(SplitBillCreate.source_event, F.data == "skip_split_event")
async def split_bill_skip_event(callback: CallbackQuery, state: FSMContext):
    await state.update_data(source_event_id=None)
    await ask_split_bill_topic(callback.message, state)
    await finalize_callback(callback, "Связка с мероприятием пропущена", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(SplitBillCreate.source_event, ~F.text.startswith("/"))
async def split_bill_source_event(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    raw = (message.text or "").strip()
    if raw.lower() == "пропустить":
        await state.update_data(source_event_id=None)
        await ask_split_bill_topic(message, state)
        return

    if not raw.isdigit():
        await answer_private_intermediate(message, state, "❌ Введите числовой event_id или нажмите «Пропустить».")
        return

    await state.update_data(source_event_id=int(raw))
    await ask_split_bill_topic(message, state)


@router.callback_query(SplitBillCreate.source_event, F.data.startswith("sb_source_"))
async def split_bill_source_event_callback(callback: CallbackQuery, state: FSMContext):
    raw_id = callback.data.removeprefix("sb_source_")
    if raw_id == "skip":
        await state.update_data(source_event_id=None)
        callback_text = "Связка с мероприятием пропущена"
    elif raw_id.isdigit():
        await state.update_data(source_event_id=int(raw_id))
        callback_text = "Мероприятие выбрано"
    else:
        await finalize_callback(callback, "Некорректный ID", show_alert=True)
        return
    await ask_split_bill_topic(callback.message, state)
    await finalize_callback(callback, callback_text, delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


async def ask_split_bill_topic(message: Message, state: FSMContext) -> None:
    topics = await get_topics_list_from_db()
    await state.set_state(SplitBillCreate.target_topic)
    if topics:
        await answer_private_intermediate(
            message,
            state,
            split_bill_step_prompt(SplitBillCreate.target_topic.state, "🗂 Выберите подгруппу для публикации разделения чека:"),
            reply_markup=choose_topic_keyboard(topics, back_callback="sb_back"),
        )
        return
    await state.update_data(thread_id=None)
    await ask_transfer_target(message, state)


@router.callback_query(SplitBillCreate.target_topic, F.data.startswith("topic_"))
async def split_bill_topic_callback(callback: CallbackQuery, state: FSMContext):
    thread_id_raw = callback.data.split("_", 1)[1]
    thread_id = int(thread_id_raw) if thread_id_raw != "0" else None
    await state.update_data(thread_id=thread_id)
    await ask_transfer_target(callback.message, state)
    await finalize_callback(callback, "Подгруппа выбрана", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


async def ask_transfer_target(message: Message, state: FSMContext) -> None:
    await state.set_state(SplitBillCreate.transfer_target)
    rows = [
        [InlineKeyboardButton(text="📱 Номер телефона", callback_data="sb_tt_phone")],
        [InlineKeyboardButton(text="💳 Номер карты", callback_data="sb_tt_card")],
        [InlineKeyboardButton(text="🔗 Ссылка на перевод", callback_data="sb_tt_link")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="sb_back")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")],
    ]
    await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_target.state, "💸 Выберите формат реквизитов для перевода:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(SplitBillCreate.transfer_target, F.data.startswith("sb_tt_"))
async def split_bill_transfer_target_type(callback: CallbackQuery, state: FSMContext):
    target_type = callback.data.removeprefix("sb_tt_")
    await state.update_data(transfer_target_type=target_type)
    await state.set_state(SplitBillCreate.transfer_target)
    await answer_private_intermediate(callback.message, state, split_bill_step_prompt(SplitBillCreate.transfer_target.state, "Введите реквизиты для перевода (телефон/карта/ссылка):"), reply_markup=cancel_keyboard(back_callback="sb_back"))
    await finalize_callback(callback, "Выбрано", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(SplitBillCreate.transfer_target, ~F.text.startswith("/"))
async def split_bill_transfer_target_value(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    value = (message.text or "").strip()
    if not value:
        await answer_private_intermediate(message, state, "❌ Реквизиты не должны быть пустыми.")
        return
    await state.update_data(transfer_target_value=value)
    await state.set_state(SplitBillCreate.transfer_bank)
    rows = [
        [InlineKeyboardButton(text="Сбер", callback_data="sb_bank_sber")],
        [InlineKeyboardButton(text="Т-банк", callback_data="sb_bank_tbank")],
        [InlineKeyboardButton(text="Альфа", callback_data="sb_bank_alfa")],
        [InlineKeyboardButton(text="Яндекс", callback_data="sb_bank_yandex")],
        [InlineKeyboardButton(text="Свой вариант", callback_data="sb_bank_other")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="sb_back")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")],
    ]
    await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_bank.state, "🏦 Выберите банк:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(SplitBillCreate.transfer_bank, F.data.startswith("sb_bank_"))
async def split_bill_bank_select(callback: CallbackQuery, state: FSMContext):
    bank = callback.data.removeprefix("sb_bank_")
    if bank == "other":
        await state.set_state(SplitBillCreate.transfer_bank_custom)
        await answer_private_intermediate(callback.message, state, split_bill_step_prompt(SplitBillCreate.transfer_bank_custom.state, "Введите название банка:"), reply_markup=cancel_keyboard(back_callback="sb_back"))
        await finalize_callback(callback, "Укажите свой банк", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)
        return
    await state.update_data(transfer_bank=bank, transfer_bank_custom=None)
    await state.set_state(SplitBillCreate.transfer_recipient_name)
    await answer_private_intermediate(callback.message, state, split_bill_step_prompt(SplitBillCreate.transfer_recipient_name.state, "Введите ФИО получателя перевода:"), reply_markup=cancel_keyboard(back_callback="sb_back"))
    await finalize_callback(callback, "Банк выбран", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(SplitBillCreate.transfer_bank_custom, ~F.text.startswith("/"))
async def split_bill_bank_custom(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    bank_name = (message.text or "").strip()
    if not bank_name:
        await answer_private_intermediate(message, state, "❌ Название банка не должно быть пустым.")
        return
    await state.update_data(transfer_bank="other", transfer_bank_custom=bank_name)
    await state.set_state(SplitBillCreate.transfer_recipient_name)
    await answer_private_intermediate(message, state, split_bill_step_prompt(SplitBillCreate.transfer_recipient_name.state, "Введите ФИО получателя перевода:"), reply_markup=cancel_keyboard(back_callback="sb_back"))


@router.message(SplitBillCreate.transfer_recipient_name, ~F.text.startswith("/"))
async def split_bill_recipient_name(message: Message, state: FSMContext):
    if not _is_private_message(message):
        return
    fio = (message.text or "").strip()
    if not fio:
        await answer_private_intermediate(message, state, "❌ ФИО не должно быть пустым.")
        return
    await state.update_data(transfer_recipient_name=fio)
    await finalize_split_bill(message, state)


def split_bill_source_event_keyboard(events: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for event in events[:6]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🆔{event['id']} · {event['title'][:24]}",
                    callback_data=f"sb_source_{event['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data="sb_source_skip")])
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data="sb_back")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("sb_join_"))
@approved_member_callback_only
async def split_bill_join_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    if not await is_member_approved(callback.from_user.id):
        await finalize_callback(callback, "Только участники группы", show_alert=True)
        return

    bill = await get_split_bill(split_id)
    if not bill or bill.get("status") != "open":
        await finalize_callback(callback, "Чек недоступен", show_alert=True)
        return

    await add_split_bill_participant(split_id, callback.from_user.id)
    await refresh_split_message(callback, split_id)
    await finalize_callback(callback, "Вы добавлены")


@router.callback_query(F.data.startswith("sb_leave_"))
@approved_member_callback_only
async def split_bill_leave_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    bill = await get_split_bill(split_id)
    if not bill or bill.get("status") != "open":
        await finalize_callback(callback, "Чек недоступен", show_alert=True)
        return

    if int(bill.get("organizer_id")) == callback.from_user.id:
        await finalize_callback(callback, "Организатор не может выйти из чека", show_alert=True)
        return

    await remove_split_bill_participant(split_id, callback.from_user.id)
    await refresh_split_message(callback, split_id)
    await finalize_callback(callback, "Вы удалены")


@router.callback_query(F.data.startswith("sb_paid_"))
@approved_member_callback_only
async def split_bill_paid_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    bill = await get_split_bill(split_id)
    if not bill or bill.get("status") != "open":
        await finalize_callback(callback, "Чек недоступен", show_alert=True)
        return

    participants = await get_split_bill_participants(split_id)
    participant_ids = {int(p["user_id"]) for p in participants}
    if callback.from_user.id not in participant_ids:
        await finalize_callback(callback, "Сначала присоединитесь", show_alert=True)
        return

    await mark_split_bill_paid(split_id, callback.from_user.id)
    await refresh_split_message(callback, split_id)
    await finalize_callback(callback, "Оплата отмечена")


@router.callback_query(F.data.startswith("sb_status_"))
@approved_member_callback_only
async def split_bill_status_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    await refresh_split_message(callback, split_id)
    await finalize_callback(callback, "Обновлено")


@router.callback_query(F.data.startswith("sb_remind_"))
@approved_member_callback_only
async def split_bill_remind_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    bill = await get_split_bill(split_id)
    if not bill or bill.get("status") != "open":
        await finalize_callback(callback, "Чек недоступен", show_alert=True)
        return
    if int(bill.get("organizer_id")) != callback.from_user.id:
        await finalize_callback(callback, "Только организатор", show_alert=True)
        return

    sent, total = await remind_unpaid_participants(callback.bot, split_id)
    if total == 0:
        await finalize_callback(callback, "Все участники уже оплатили", show_alert=True)
        return
    await finalize_callback(callback, f"Напоминания: {sent} из {total}")


@router.callback_query(F.data.startswith("sb_close_"))
@approved_member_callback_only
async def split_bill_close_callback(callback: CallbackQuery):
    split_id = int(callback.data.rsplit("_", 1)[-1])
    bill = await get_split_bill(split_id)
    if not bill:
        await finalize_callback(callback, "Чек не найден", show_alert=True)
        return
    if int(bill.get("organizer_id")) != callback.from_user.id:
        await finalize_callback(callback, "Только организатор", show_alert=True)
        return

    if not await close_bill_if_ready(split_id):
        await finalize_callback(callback, "Не все участники оплатили", show_alert=True)
        return

    await refresh_split_message(callback, split_id)
    await finalize_callback(callback, "Чек закрыт")


@router.message(Command("split_bill_add"))
async def cmd_split_bill_add(message: Message):
    args = parse_args(message)
    split_id = parse_int_arg(args[0]) if len(args) == 2 else None
    if split_id is None:
        await message.answer("Использование: /split_bill_add <split_id> <user_id|@username>")
        return
    user_id = await _resolve_user_id(args[1], message)
    if not user_id:
        await message.answer("❌ Не удалось определить пользователя. Используйте user_id или @username.")
        return
    if not await is_member_approved(user_id):
        await message.answer("❌ Пользователь не является актуальным участником группы.")
        return

    bill = await get_split_bill(split_id)
    if not bill:
        await message.answer("❌ Событие не найдено.")
        return
    if int(bill.get("organizer_id")) != message.from_user.id:
        await message.answer("❌ Добавлять участников может только организатор.")
        return
    if bill.get("status") != "open":
        await message.answer("❌ Событие закрыто.")
        return

    await add_split_bill_participant(split_id, user_id)
    await refresh_published_split_message(message.bot, split_id)
    await message.answer(f"✅ Участник {user_id} добавлен в чек #{split_id}.")


@router.message(Command("split_bill_remove"))
async def cmd_split_bill_remove(message: Message):
    args = parse_args(message)
    split_id = parse_int_arg(args[0]) if len(args) == 2 else None
    if split_id is None:
        await message.answer("Использование: /split_bill_remove <split_id> <user_id|@username>")
        return
    user_id = await _resolve_user_id(args[1], message)
    if not user_id:
        await message.answer("❌ Не удалось определить пользователя. Используйте user_id или @username.")
        return

    bill = await get_split_bill(split_id)
    if not bill:
        await message.answer("❌ Событие не найдено.")
        return
    if int(bill.get("organizer_id")) != message.from_user.id:
        await message.answer("❌ Удалять участников может только организатор.")
        return
    if bill.get("status") != "open":
        await message.answer("❌ Событие закрыто.")
        return

    await remove_split_bill_participant(split_id, user_id)
    await refresh_published_split_message(message.bot, split_id)
    await message.answer(f"🗑 Участник {user_id} удалён из чека #{split_id}.")
