"""Generate bot/database_pg.py from bot/database_ydb.py with a thin compat layer."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bot" / "database_ydb.py"
DST = ROOT / "bot" / "database_pg.py"

HEADER = '''"""PostgreSQL database layer for Bot Adventure Time."""

import logging
import json
import time
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from bot.db_pool import execute, fetch, get_pool

logger = logging.getLogger(__name__)


class _CompatRow:
    def __init__(self, record):
        self._record = record

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._record[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _CompatResultSet:
    def __init__(self, records):
        self.rows = [_CompatRow(record) for record in records]


async def _run_query(query: str, parameters: dict | None = None):
    records = await fetch(query, parameters)
    return [_CompatResultSet(records)]


async def _run_execute(query: str, parameters: dict | None = None) -> None:
    await execute(query, parameters)


'''

INIT_DB = '''
async def init_db():
    """Creates tables on first startup."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            notification_settings TEXT DEFAULT 'all',
            stats_count BIGINT DEFAULT 0,
            birth_date TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id BIGINT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            date_time TEXT NOT NULL,
            duration_minutes BIGINT,
            period_end TEXT,
            location TEXT,
            price_total DOUBLE PRECISION,
            price_per_person DOUBLE PRECISION,
            participant_limit BIGINT,
            thread_id BIGINT,
            message_id BIGINT,
            creator_id BIGINT,
            responsible_id BIGINT,
            weather_info TEXT,
            carpool_enabled BOOLEAN DEFAULT false,
            status TEXT DEFAULT 'active',
            category TEXT,
            created_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS participants (
            id BIGINT PRIMARY KEY,
            event_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            status TEXT,
            car_seats BIGINT,
            passenger_of BIGINT,
            joined_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reminder_jobs (
            id BIGINT PRIMARY KEY,
            event_id BIGINT NOT NULL,
            interval_seconds BIGINT,
            scheduled_time TIMESTAMPTZ,
            sent BOOLEAN DEFAULT false
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forum_topics (
            id BIGINT PRIMARY KEY,
            message_thread_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            is_closed BOOLEAN DEFAULT false,
            is_hidden BOOLEAN DEFAULT false,
            discovered_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_category_subscriptions (
            user_id BIGINT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, category)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS random_meeting_opt_in (
            user_id BIGINT PRIMARY KEY,
            is_enabled BOOLEAN NOT NULL,
            updated_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pending_users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            status TEXT,
            created_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fsm_states (
            bot_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            thread_id BIGINT NOT NULL DEFAULT 0,
            business_connection_id TEXT NOT NULL DEFAULT '',
            destiny TEXT NOT NULL,
            state TEXT,
            data_json TEXT,
            updated_at TIMESTAMPTZ,
            PRIMARY KEY (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS approved_members (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            join_date TIMESTAMPTZ,
            intro_status TEXT DEFAULT 'pending'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS command_usage_daily (
            usage_date TEXT NOT NULL,
            role TEXT NOT NULL,
            command TEXT NOT NULL,
            usage_count BIGINT NOT NULL,
            PRIMARY KEY (usage_date, role, command)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_events (
            id BIGINT PRIMARY KEY,
            group_id BIGINT NOT NULL,
            organizer_id BIGINT NOT NULL,
            title TEXT,
            total_amount DOUBLE PRECISION NOT NULL,
            transfer_target_type TEXT,
            transfer_target_value TEXT,
            transfer_bank TEXT,
            transfer_bank_custom TEXT,
            transfer_recipient_name TEXT,
            status TEXT NOT NULL,
            source_event_id BIGINT,
            thread_id BIGINT,
            message_id BIGINT,
            created_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_participants (
            split_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            is_paid BOOLEAN NOT NULL,
            share_amount DOUBLE PRECISION NOT NULL,
            joined_at TIMESTAMPTZ,
            PRIMARY KEY (split_id, user_id)
        )
        """,
    ]

    for statement in statements:
        await execute(statement.strip())

    for column_def in ("responsible_id BIGINT", "period_end TEXT"):
        column_name = column_def.split()[0]
        try:
            await execute(f"ALTER TABLE events ADD COLUMN IF NOT EXISTS {column_def}")
            logger.info("Ensured column events.%s", column_name)
        except Exception as exc:
            logger.warning("Could not alter events.%s: %s", column_name, exc)

    for column_def in (
        "title TEXT",
        "transfer_target_type TEXT",
        "transfer_target_value TEXT",
        "transfer_bank TEXT",
        "transfer_bank_custom TEXT",
        "transfer_recipient_name TEXT",
        "thread_id BIGINT",
        "message_id BIGINT",
    ):
        column_name = column_def.split()[0]
        try:
            await execute(f"ALTER TABLE split_bill_events ADD COLUMN IF NOT EXISTS {column_def}")
            logger.info("Ensured column split_bill_events.%s", column_name)
        except Exception as exc:
            logger.warning("Could not alter split_bill_events.%s: %s", column_name, exc)

    logger.info("PostgreSQL tables created or already exist")


'''


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    marker = "async def get_or_create_user"
    idx = src.find(marker)
    if idx == -1:
        raise RuntimeError("marker not found")
    body = src[idx:]

    replacements = [
        ('COALESCE(username, "")', "COALESCE(username, '')"),
        ("UPSERT INTO pending_users (user_id, username, full_name, status)\n            VALUES ($user_id, $username, $full_name, $status)",
         "INSERT INTO pending_users (user_id, username, full_name, status, created_at)\n            VALUES ($user_id, $username, $full_name, $status, NOW())\n            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, status = EXCLUDED.status"),
        ("UPSERT INTO approved_members (user_id, username, full_name, intro_status)\n            VALUES ($user_id, $username, $full_name, $intro_status)",
         "INSERT INTO approved_members (user_id, username, full_name, intro_status)\n            VALUES ($user_id, $username, $full_name, $intro_status)\n            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, intro_status = EXCLUDED.intro_status"),
        ("UPSERT INTO random_meeting_opt_in (user_id, is_enabled)\n            VALUES ($user_id, $is_enabled)",
         "INSERT INTO random_meeting_opt_in (user_id, is_enabled, updated_at)\n            VALUES ($user_id, $is_enabled, NOW())\n            ON CONFLICT (user_id) DO UPDATE SET is_enabled = EXCLUDED.is_enabled, updated_at = NOW()"),
        ("UPSERT INTO forum_topics (id, message_thread_id, name, is_closed, is_hidden)\n            VALUES ($id, $message_thread_id, $name, false, false)",
         "INSERT INTO forum_topics (id, message_thread_id, name, is_closed, is_hidden)\n            VALUES ($id, $message_thread_id, $name, false, false)\n            ON CONFLICT (id) DO UPDATE SET message_thread_id = EXCLUDED.message_thread_id, name = EXCLUDED.name"),
        ("UPSERT INTO command_usage_daily (usage_date, role, command, usage_count)\n                VALUES ($usage_date, $role, $command, $usage_count)",
         "INSERT INTO command_usage_daily (usage_date, role, command, usage_count)\n                VALUES ($usage_date, $role, $command, $usage_count)\n                ON CONFLICT (usage_date, role, command) DO UPDATE SET usage_count = EXCLUDED.usage_count"),
        ("UPSERT INTO split_bill_events\n            (id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, created_at)\n            VALUES ($id, $group_id, $organizer_id, $title, $total_amount, $transfer_target_type, $transfer_target_value, $transfer_bank, $transfer_bank_custom, $transfer_recipient_name, $status, $source_event_id, $created_at)",
         "INSERT INTO split_bill_events\n            (id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, created_at)\n            VALUES ($id, $group_id, $organizer_id, $title, $total_amount, $transfer_target_type, $transfer_target_value, $transfer_bank, $transfer_bank_custom, $transfer_recipient_name, $status, $source_event_id, $created_at)\n            ON CONFLICT (id) DO NOTHING"),
        ("UPSERT INTO split_bill_participants (split_id, user_id, is_paid, share_amount, joined_at)\n            VALUES ($split_id, $user_id, false, 0.0, $joined_at)",
         "INSERT INTO split_bill_participants (split_id, user_id, is_paid, share_amount, joined_at)\n            VALUES ($split_id, $user_id, false, 0.0, $joined_at)\n            ON CONFLICT (split_id, user_id) DO UPDATE SET is_paid = EXCLUDED.is_paid, share_amount = EXCLUDED.share_amount, joined_at = EXCLUDED.joined_at"),
    ]
    for old, new in replacements:
        body = body.replace(old, new)

    # Replace pool.retry_operation blocks
    body = re.sub(
        r"await pool\.retry_operation\(\s*lambda session: session\.transaction\(\)\.execute\(",
        "await _run_query(",
        body,
    )
    body = re.sub(
        r"await pool\.retry_operation_async\(_query\)",
        "await _query()",
        body,
    )
    body = re.sub(
        r"await pool\.retry_operation_async\(_query_users\)",
        "await _query_users()",
        body,
    )
    body = re.sub(
        r",?\s*commit_tx=True,\s*\)\s*\)",
        ")",
        body,
    )

    # get_user_id_by_username inner queries
    body = body.replace("DECLARE $username AS Utf8;\n\n        $uname = CAST($username AS Utf8);\n\n        ", "")
    body = body.replace("$uname", "$username")

    body = re.sub(
        r"async def _query\(session\):\s*query = \"\"\"",
        'async def _query():\n        query = """',
        body,
        count=1,
    )
    body = re.sub(
        r"rows = await session\.transaction\(\)\.execute\(query, \{\"(\$username)\": normalized\}, commit_tx=True\)\s*return rows\[0\]\.rows if rows else \[\]",
        "return await _run_query(query, {\"username\": normalized})",
        body,
        count=1,
    )
    body = re.sub(
        r"async def _query_users\(session\):\s*query = \"\"\"",
        'async def _query_users():\n        query = """',
        body,
        count=1,
    )
    body = re.sub(
        r"rows = await session\.transaction\(\)\.execute\(query, \{\"(\$username)\": normalized\}, commit_tx=True\)\s*return rows\[0\]\.rows if rows else \[\]",
        "return await _run_query(query, {\"username\": normalized})",
        body,
        count=1,
    )
    body = body.replace("rows = await _query()", "result = await _query()\n        rows = result[0].rows")
    body = body.replace("rows = await _query_users()", "result = await _query_users()\n        rows = result[0].rows")

    # set_driver / set_passenger multi-statement
    body = body.replace(
        """            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id;

            UPSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, 'driver', $car_seats, 0);""",
        """            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id""",
    )
    body = body.replace(
        """            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id;

            UPSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, 'passenger', 0, $driver_id);""",
        """            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id""",
    )

    driver_block = """    await _run_query(
        \"\"\"
        DELETE FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        \"\"\",
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
        },
    )
    await _run_execute(
        \"\"\"
        INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
        VALUES ($id, $event_id, $user_id, 'driver', $car_seats, 0)
        \"\"\",
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "car_seats": int(car_seats),
        },
    )"""

    passenger_block = """    await _run_query(
        \"\"\"
        DELETE FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        \"\"\",
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
        },
    )
    await _run_execute(
        \"\"\"
        INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
        VALUES ($id, $event_id, $user_id, 'passenger', 0, $driver_id)
        \"\"\",
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "driver_id": int(driver_id),
        },
    )"""

    body = body.replace(
        """    await _run_query(
        \"\"\"
            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id
            \"\"\",
        parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "car_seats": int(car_seats),
            },
    )
    return True


async def set_passenger""",
        driver_block + "\n    return True\n\n\nasync def set_passenger",
    )

    body = body.replace(
        """    await _run_query(
        \"\"\"
            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id
            \"\"\",
        parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "driver_id": int(driver_id),
            },
    )
    return True


async def add_driver""",
        passenger_block + "\n    return True\n\n\nasync def add_driver",
    )

    # Remove schema limit error handling
    body = body.replace("_is_table_missing_error(exc, \"command_usage_daily\")", "False")

    output = HEADER + INIT_DB.strip() + "\n\n\n" + body
    DST.write_text(output, encoding="utf-8")
    print(f"Wrote {DST} ({len(output.splitlines())} lines)")


if __name__ == "__main__":
    main()
