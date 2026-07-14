from __future__ import annotations

import logging
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import GROUP_ID
from bot.database import (
    add_split_bill_participant,
    close_split_bill,
    create_split_bill,
    get_event_participant_ids,
    get_split_bill,
    get_split_bill_participants,
    mark_split_bill_paid,
    remove_split_bill_participant,
    update_split_bill_message_id,
)
from bot.utils.helpers import get_user_mentions
from bot.utils.design import BRAND, brand_voice, card_cta, card_header, card_section, money_collection_line
from bot.utils.notifications import send_private_dm
from bot.keyboards import split_bill_actions, split_bill_organizer_keyboard

from bot.utils.ui import answer_private_final

logger = logging.getLogger(__name__)


def parse_args(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


def build_payment_progress_bar(paid_count: int, total_count: int, width: int = 6) -> str:
    """Текстовая шкала оплаты вида ████░░ 4/6 оплатили."""
    if total_count <= 0:
        return f"{'░' * width} 0/0 оплатили"
    filled_units = round((paid_count / total_count) * width)
    filled_units = max(0, min(width, filled_units))
    return f"{'█' * filled_units}{'░' * (width - filled_units)} {paid_count}/{total_count} оплатили"


async def format_split_bill_text(
    split_id: int,
    bot,
    bill: dict | None = None,
    participants: list[dict] | None = None,
) -> str:
    bill = bill or await get_split_bill(split_id)
    if not bill:
        return "❌ Событие разделения чека не найдено."

    participants = participants if participants is not None else await get_split_bill_participants(split_id)
    mention_ids = {int(bill["organizer_id"]), *(int(p["user_id"]) for p in participants)}
    mentions = await get_user_mentions(mention_ids, bot)
    organizer_mention = mentions.get(int(bill["organizer_id"]), f"id{bill['organizer_id']}")
    paid_count = sum(1 for p in participants if p.get("is_paid"))
    waiting_count = max(0, len(participants) - paid_count)
    progress_bar = build_payment_progress_bar(paid_count, len(participants))
    total_amount_value = float(bill.get("total_amount") or 0)
    collected_amount = sum(float(p.get("share_amount") or 0) for p in participants if p.get("is_paid"))
    remaining_amount = max(0.0, total_amount_value - collected_amount)
    bank = (
        bill.get("transfer_bank_custom")
        if bill.get("transfer_bank") == "other"
        else bill.get("transfer_bank")
    ) or "—"
    title = escape(str(bill.get("title") or "—"))
    status = escape(str(bill.get("status") or "—"))
    total_amount_text = escape(str(bill.get("total_amount") or "0"))
    remaining_text = f"{remaining_amount:.0f}"

    lines = [
        *card_header(
            BRAND["money"],
            "Разделение чека",
            f"Осталось собрать {remaining_text} ₽",
        ),
        f"🆔 ID: <code>{split_id}</code>",
        f"🧾 Название: <b>{title}</b>",
        f"📌 Статус: <b>{status}</b>",
        f"👤 Организатор: {organizer_mention}",
        f"💰 Сумма: <b>{total_amount_text} ₽</b>",
        *card_section(
            "Сбор средств",
            [
                money_collection_line(collected_amount, total_amount_value),
                f"Осталось: <b>{remaining_text} ₽</b>",
                progress_bar,
                f"Оплачено: <b>{paid_count}</b> / ждём: <b>{waiting_count}</b>",
                f"👥 участников: <b>{len(participants)}</b>",
            ],
        ),
        *card_section(
            "Реквизиты",
            [
                f"• Тип: {escape(str(bill.get('transfer_target_type') or '—'))}",
                f"• Куда: {escape(str(bill.get('transfer_target_value') or '—'))}",
                f"• Банк: {escape(str(bank))}",
                f"• Получатель: {escape(str(bill.get('transfer_recipient_name') or '—'))}",
            ],
        ),
    ]

    checklist_lines: list[str] = []
    if not participants:
        checklist_lines.append("—")
    else:
        for p in participants:
            uid = int(p["user_id"])
            paid = "✅" if p.get("is_paid") else "⏳"
            mention = mentions.get(uid, f"id{uid}")
            checklist_lines.append(f"{paid} {mention} — {p.get('share_amount')} ₽")

    lines.extend(card_section("Чек-лист оплат", checklist_lines))
    lines.extend(card_cta("Нажми «Оплатил(а)», когда переведёшь свою долю."))
    return "\n".join(lines)


async def finalize_split_bill(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = float(data["total_amount"])
    source_event_id = data.get("source_event_id")
    creator_id = int(data["creator_id"])
    thread_id = data.get("thread_id")

    split_id = await create_split_bill(
        group_id=GROUP_ID,
        organizer_id=creator_id,
        title=data.get("title"),
        total_amount=amount,
        transfer_target_type=data.get("transfer_target_type"),
        transfer_target_value=data.get("transfer_target_value"),
        transfer_bank=data.get("transfer_bank"),
        transfer_bank_custom=data.get("transfer_bank_custom"),
        transfer_recipient_name=data.get("transfer_recipient_name"),
        source_event_id=source_event_id,
    )

    initial_participants: list[int] = []
    if source_event_id:
        initial_participants = await get_event_participant_ids(source_event_id)

    if creator_id not in initial_participants:
        initial_participants.append(creator_id)

    for uid in sorted(set(initial_participants)):
        await add_split_bill_participant(split_id, uid)

    text = await format_split_bill_text(split_id, message.bot)
    sent = await message.bot.send_message(
        GROUP_ID,
        text,
        message_thread_id=thread_id,
        parse_mode="HTML",
        reply_markup=split_bill_actions(split_id),
    )
    await update_split_bill_message_id(split_id, thread_id, sent.message_id)

    await answer_private_final(
        message,
        state,
        f"✅ {brand_voice('split_bill_created')}\n"
        f"Чек «{data.get('title') or f'#{split_id}'}»\n"
        f"ID: {split_id}\n"
        f"Ссылка: https://t.me/c/{str(GROUP_ID).replace('-100', '')}/{sent.message_id}",
        reply_markup=split_bill_organizer_keyboard(split_id),
    )
    await state.clear()


async def refresh_split_message(callback: CallbackQuery, split_id: int) -> None:
    bill = await get_split_bill(split_id)
    if not bill:
        return
    participants = await get_split_bill_participants(split_id)
    text = await format_split_bill_text(split_id, callback.bot, bill=bill, participants=participants)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=split_bill_actions(split_id))
    except Exception as exc:
        logger.warning("Не удалось обновить split-bill карточку split_id=%s: %s", split_id, exc)


async def refresh_published_split_message(bot, split_id: int) -> None:
    bill = await get_split_bill(split_id)
    if not bill or not bill.get("message_id"):
        return
    participants = await get_split_bill_participants(split_id)
    text = await format_split_bill_text(split_id, bot, bill=bill, participants=participants)
    try:
        await bot.edit_message_text(
            chat_id=GROUP_ID,
            message_id=int(bill["message_id"]),
            text=text,
            parse_mode="HTML",
            reply_markup=split_bill_actions(split_id),
        )
    except Exception as exc:
        logger.warning("Не удалось обновить опубликованную split-bill карточку split_id=%s: %s", split_id, exc)


async def close_bill_if_ready(split_id: int) -> bool:
    participants = await get_split_bill_participants(split_id)
    if not participants or any(not bool(p.get("is_paid")) for p in participants):
        return False
    await close_split_bill(split_id)
    return True


async def remind_unpaid_participants(bot, split_id: int) -> tuple[int, int]:
    """Отправляет напоминания неоплатившим. Возвращает (отправлено, всего должников)."""
    bill = await get_split_bill(split_id)
    if not bill or bill.get("status") != "open":
        return 0, 0

    participants = await get_split_bill_participants(split_id)
    unpaid = [p for p in participants if not p.get("is_paid")]
    if not unpaid:
        return 0, 0

    title = bill.get("title") or f"#{split_id}"
    share_hint = unpaid[0].get("share_amount")
    text = (
        f"🔔 Напоминание по чеку «{title}»\n"
        f"Переведи свою долю"
        + (f" ({share_hint} ₽)" if share_hint else "")
        + " и отметь «Оплатил(а)» в карточке."
    )

    sent = 0
    for participant in unpaid:
        if await send_private_dm(
            bot,
            int(participant["user_id"]),
            text,
            parse_mode=None,
            notification_kind="personal",
        ):
            sent += 1
    return sent, len(unpaid)


__all__ = [
    "add_split_bill_participant",
    "close_bill_if_ready",
    "finalize_split_bill",
    "format_split_bill_text",
    "get_split_bill",
    "get_split_bill_participants",
    "build_payment_progress_bar",
    "mark_split_bill_paid",
    "parse_args",
    "refresh_split_message",
    "refresh_published_split_message",
    "remove_split_bill_participant",
    "remind_unpaid_participants",
    "split_bill_actions",
]
