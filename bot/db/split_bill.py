"""Split bill management."""

from datetime import datetime, timezone
from typing import Any, Optional

from .participants import get_main_participants
from ._core import _normalize_row, _run_execute, _run_query


async def create_split_bill(
    *,
    group_id: int,
    organizer_id: int,
    title: str | None,
    total_amount: float,
    transfer_target_type: str | None = None,
    transfer_target_value: str | None = None,
    transfer_bank: str | None = None,
    transfer_bank_custom: str | None = None,
    transfer_recipient_name: str | None = None,
    source_event_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    result = await _run_query(
        """
        SELECT COALESCE(MAX(id), 0) + 1 AS new_id FROM split_bill_events
        """,
    )
    split_id = int(result[0].rows[0].new_id)

    await _run_query(
        """
        INSERT INTO split_bill_events
        (id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, created_at)
        VALUES ($id, $group_id, $organizer_id, $title, $total_amount, $transfer_target_type, $transfer_target_value, $transfer_bank, $transfer_bank_custom, $transfer_recipient_name, $status, $source_event_id, $created_at)
        ON CONFLICT (id) DO NOTHING
        """,
        parameters={
            "id": split_id,
            "group_id": int(group_id),
            "organizer_id": int(organizer_id),
            "title": (title or "").strip() or None,
            "total_amount": float(total_amount),
            "transfer_target_type": transfer_target_type,
            "transfer_target_value": transfer_target_value,
            "transfer_bank": transfer_bank,
            "transfer_bank_custom": transfer_bank_custom,
            "transfer_recipient_name": transfer_recipient_name,
            "status": "open",
            "source_event_id": source_event_id,
            "created_at": now,
        },
    )
    return split_id


async def get_split_bill(split_id: int) -> Optional[dict[str, Any]]:
    result = await _run_query(
        """
        SELECT id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, thread_id, message_id, created_at, closed_at
        FROM split_bill_events
        WHERE id = $split_id
        """,
        parameters={"split_id": int(split_id)},
    )
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def update_split_bill_message_id(split_id: int, thread_id: int | None, message_id: int) -> None:
    """Сохраняет id опубликованной split-bill карточки для последующих refresh-обновлений."""
    await _run_query(
        """
        UPDATE split_bill_events
        SET thread_id = $thread_id, message_id = $message_id
        WHERE id = $split_id
        """,
        parameters={
            "split_id": int(split_id),
            "thread_id": int(thread_id) if thread_id is not None else None,
            "message_id": int(message_id),
        },
    )


async def get_event_participant_ids(event_id: int) -> list[int]:
    return await get_main_participants(event_id)


async def get_split_bill_participants(split_id: int) -> list[dict[str, Any]]:
    result = await _run_query(
        """
        SELECT user_id, is_paid, share_amount, joined_at
        FROM split_bill_participants
        WHERE split_id = $split_id
        ORDER BY joined_at
        """,
        parameters={"split_id": int(split_id)},
    )
    return [_normalize_row(row) for row in result[0].rows]


async def recalculate_split_bill_shares(split_id: int) -> None:
    bill = await get_split_bill(split_id)
    if not bill:
        return
    participants = await get_split_bill_participants(split_id)
    if not participants:
        return
    share = round(float(bill["total_amount"]) / len(participants), 2)
    for participant in participants:
        await _run_execute(
            """
            UPDATE split_bill_participants
            SET share_amount = $share_amount
            WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={
                "split_id": int(split_id),
                "user_id": int(participant["user_id"]),
                "share_amount": share,
            },
        )


async def add_split_bill_participant(split_id: int, user_id: int) -> None:
    await _run_query(
        """
        INSERT INTO split_bill_participants (split_id, user_id, is_paid, share_amount, joined_at)
        VALUES ($split_id, $user_id, false, 0.0, $joined_at)
        ON CONFLICT (split_id, user_id) DO UPDATE SET is_paid = EXCLUDED.is_paid, share_amount = EXCLUDED.share_amount, joined_at = EXCLUDED.joined_at
        """,
        parameters={
            "split_id": int(split_id),
            "user_id": int(user_id),
            "joined_at": datetime.utcnow(),
        },
    )
    await recalculate_split_bill_shares(split_id)


async def remove_split_bill_participant(split_id: int, user_id: int) -> None:
    await _run_query(
        """
        DELETE FROM split_bill_participants WHERE split_id = $split_id AND user_id = $user_id
        """,
        parameters={"split_id": int(split_id), "user_id": int(user_id)},
    )
    await recalculate_split_bill_shares(split_id)


async def mark_split_bill_paid(split_id: int, user_id: int) -> None:
    await _run_query(
        """
        UPDATE split_bill_participants
        SET is_paid = true
        WHERE split_id = $split_id AND user_id = $user_id
        """,
        parameters={"split_id": int(split_id), "user_id": int(user_id)},
    )


async def close_split_bill(split_id: int) -> None:
    await _run_query(
        """
        UPDATE split_bill_events
        SET status = 'closed', closed_at = $closed_at
        WHERE id = $split_id
        """,
        parameters={"split_id": int(split_id), "closed_at": datetime.utcnow()},
    )
