"""Database schema initialization."""

import logging

from bot.db_pool import execute

logger = logging.getLogger(__name__)


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
            link TEXT,
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
            guest_count BIGINT DEFAULT 0,
            joined_at TIMESTAMPTZ
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
        CREATE TABLE IF NOT EXISTS user_command_usage_daily (
            user_id BIGINT NOT NULL,
            usage_date TEXT NOT NULL,
            usage_count BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, usage_date)
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
        """
        CREATE TABLE IF NOT EXISTS attendance_responses (
            event_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            response TEXT NOT NULL DEFAULT 'pending',
            prompted_at TIMESTAMPTZ,
            responded_at TIMESTAMPTZ,
            PRIMARY KEY (event_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pending_notifications (
            id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            parse_mode TEXT,
            disable_web_page_preview BOOLEAN NOT NULL DEFAULT true,
            reply_markup_json TEXT,
            created_at TIMESTAMPTZ,
            sent_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'pending'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS birthday_greetings_log (
            user_id BIGINT NOT NULL,
            greeted_on DATE NOT NULL,
            created_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, greeted_on)
        )
        """,
    ]

    for statement in statements:
        await execute(statement.strip())

    from bot.db.ids import ensure_id_sequences

    await ensure_id_sequences()

    # Deduplicate participants before UNIQUE constraint (keep highest id).
    try:
        await execute(
            """
            DELETE FROM participants a
            USING participants b
            WHERE a.event_id = b.event_id
              AND a.user_id = b.user_id
              AND a.id < b.id
            """
        )
    except Exception as exc:
        logger.warning("Could not dedupe participants: %s", exc)

    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_participants_event_id_status ON participants (event_id, status)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_participants_event_id_user_id ON participants (event_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_status_date_time ON events (status, date_time)",
        "CREATE INDEX IF NOT EXISTS idx_fsm_states_user_id_chat_id ON fsm_states (user_id, chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_fsm_states_updated_at ON fsm_states (updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_user_category_subscriptions_user_id_category ON user_category_subscriptions (user_id, category)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_responses_event_id ON attendance_responses (event_id)",
        "CREATE INDEX IF NOT EXISTS idx_pending_notifications_status_created ON pending_notifications (status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_users_birth_date ON users (birth_date)",
    ]
    for statement in index_statements:
        await execute(statement)

    for column_def in ("responsible_id BIGINT", "period_end TEXT", "link TEXT"):
        column_name = column_def.split()[0]
        try:
            await execute(f"ALTER TABLE events ADD COLUMN IF NOT EXISTS {column_def}")
            logger.info("Ensured column events.%s", column_name)
        except Exception as exc:
            logger.warning("Could not alter events.%s: %s", column_name, exc)

    try:
        await execute(
            "ALTER TABLE participants ADD COLUMN IF NOT EXISTS guest_count BIGINT DEFAULT 0"
        )
        logger.info("Ensured column participants.guest_count")
    except Exception as exc:
        logger.warning("Could not alter participants.guest_count: %s", exc)

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

    try:
        await execute("DROP TABLE IF EXISTS reminder_jobs")
        logger.info("Dropped legacy table reminder_jobs")
    except Exception as exc:
        logger.warning("Could not drop reminder_jobs: %s", exc)

    logger.info("PostgreSQL tables created or already exist")
