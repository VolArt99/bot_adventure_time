"""Deferred private notifications (quiet hours queue)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from bot.db.ids import next_id
from ._core import _normalize_row, _run_execute, _run_query


async def enqueue_pending_notification(
    *,
    user_id: int,
    text: str,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
    reply_markup_json: str | None = None,
) -> int:
    notification_id = await next_id("pending_notifications_id_seq")
    now = datetime.now(timezone.utc)
    await _run_execute(
        """
        INSERT INTO pending_notifications (
            id, user_id, text, parse_mode, disable_web_page_preview,
            reply_markup_json, created_at, status
        ) VALUES (
            $id, $user_id, $text, $parse_mode, $disable_web_page_preview,
            $reply_markup_json, $created_at, 'pending'
        )
        """,
        parameters={
            "id": notification_id,
            "user_id": int(user_id),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": bool(disable_web_page_preview),
            "reply_markup_json": reply_markup_json,
            "created_at": now,
        },
    )
    return notification_id


async def claim_pending_notifications(limit: int = 100) -> list[dict[str, Any]]:
    """Atomically claims a batch of pending rows for sending."""
    result = await _run_query(
        """
        WITH cte AS (
            SELECT id
            FROM pending_notifications
            WHERE status = 'pending'
            ORDER BY created_at, id
            LIMIT $limit
            FOR UPDATE SKIP LOCKED
        )
        UPDATE pending_notifications AS p
        SET status = 'sending'
        FROM cte
        WHERE p.id = cte.id
        RETURNING
            p.id, p.user_id, p.text, p.parse_mode,
            p.disable_web_page_preview, p.reply_markup_json
        """,
        parameters={"limit": int(limit)},
    )
    return [_normalize_row(row) for row in result[0].rows]


async def mark_pending_notification_sent(notification_id: int) -> None:
    await _run_execute(
        """
        UPDATE pending_notifications
        SET status = 'sent', sent_at = $sent_at
        WHERE id = $id
        """,
        parameters={
            "id": int(notification_id),
            "sent_at": datetime.now(timezone.utc),
        },
    )


async def mark_pending_notification_failed(notification_id: int) -> None:
    await _run_execute(
        """
        UPDATE pending_notifications
        SET status = 'failed', sent_at = $sent_at
        WHERE id = $id
        """,
        parameters={
            "id": int(notification_id),
            "sent_at": datetime.now(timezone.utc),
        },
    )


async def cleanup_old_pending_notifications(days: int = 14) -> int:
    result = await _run_query(
        """
        DELETE FROM pending_notifications
        WHERE status IN ('sent', 'failed')
          AND COALESCE(sent_at, created_at) < NOW() - ($days || ' days')::interval
        RETURNING id
        """,
        parameters={"days": int(days)},
    )
    return len(result[0].rows)


def serialize_inline_keyboard(reply_markup) -> str | None:
    if reply_markup is None:
        return None
    rows = getattr(reply_markup, "inline_keyboard", None)
    if not rows:
        return None
    payload = []
    for row in rows:
        payload.append(
            [
                {
                    "text": button.text,
                    "callback_data": button.callback_data,
                }
                for button in row
                if getattr(button, "callback_data", None)
            ]
        )
    return json.dumps(payload, ensure_ascii=False)


def deserialize_inline_keyboard(raw: str | None):
    if not raw:
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    payload = json.loads(raw)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=item["text"], callback_data=item["callback_data"])
                for item in row
            ]
            for row in payload
        ]
    )
