# работа с YDB (Managed Service for YDB)

import os
import logging
import json
import base64
import ast
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from functools import wraps
import time

import ydb
import ydb.aio
import ydb.iam
from typing import Optional, List, Dict, Any
from bot.utils.metrics import LatencyMetrics

logger = logging.getLogger(__name__)

# Конфигурация подключения к YDB
YDB_ENDPOINT = os.getenv("YDB_ENDPOINT")
YDB_DATABASE = os.getenv("YDB_DATABASE")
YDB_SESSION_POOL_SIZE = max(1, int(os.getenv("YDB_SESSION_POOL_SIZE", "30")))
YDB_PATCH_TX_EXECUTE = os.getenv("YDB_PATCH_TX_EXECUTE", "1") == "1"

# Глобальные переменные для драйвера и пула сессий
_driver = None
_pool = None
_tx_execute_patched = False
_ydb_latency_metrics = LatencyMetrics(name="ydb_query", window_size=5000, log_every=200)


def _infer_ydb_type(value: Any, param_name: str):
    if isinstance(value, bool):
        return ydb.PrimitiveType.Bool
    if isinstance(value, int):
        if param_name in {"limit", "offset"}:
            return ydb.PrimitiveType.Uint64        
        return ydb.PrimitiveType.Int64
    if isinstance(value, float):
        return ydb.PrimitiveType.Double
    if isinstance(value, bytes):
        return ydb.PrimitiveType.String
    if isinstance(value, datetime):
        return ydb.PrimitiveType.Timestamp
    if value is None:
        if param_name.endswith("_id") or param_name == "id":
            return ydb.OptionalType(ydb.PrimitiveType.Int64)
        return ydb.OptionalType(ydb.PrimitiveType.Utf8)
    return ydb.PrimitiveType.Utf8


def _yql_type_name(ydb_type: Any) -> str:
    if isinstance(ydb_type, ydb.OptionalType):
        return f"{_yql_type_name(ydb_type.item)}?"

    primitive_names = {
        ydb.PrimitiveType.Bool: "Bool",
        ydb.PrimitiveType.Int64: "Int64",
        ydb.PrimitiveType.Uint64: "Uint64",
        ydb.PrimitiveType.Double: "Double",
        ydb.PrimitiveType.String: "String",
        ydb.PrimitiveType.Timestamp: "Timestamp",
        ydb.PrimitiveType.Utf8: "Utf8",
    }
    return primitive_names.get(ydb_type, "Utf8")


def _normalize_parameters(parameters: Dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    prefixed: dict[str, Any] = {}
    types: dict[str, Any] = {}
    for name, value in parameters.items():
        prefixed_name = name if name.startswith("$") else f"${name}"
        prefixed[prefixed_name] = value
        types[prefixed_name] = _infer_ydb_type(value, prefixed_name.lstrip("$"))
    return prefixed, types


def _build_query_with_declares(query: str, types: dict[str, Any]) -> str:
    if "DECLARE $" in query:
        return query
    declares = [f"DECLARE {name} AS {_yql_type_name(ydb_type)};" for name, ydb_type in types.items()]
    return "\n".join(declares) + "\n" + query


def install_ydb_execute_parameter_patch() -> None:
    """Изолированно включает совместимость старых вызовов execute(parameters=dict)."""
    global _tx_execute_patched
    if _tx_execute_patched or not YDB_PATCH_TX_EXECUTE:
        return

    original_sync = ydb.table.TxContext.execute
    original_async = ydb.aio.table.TxContext.execute

    @wraps(original_sync)
    def patched_sync(self, query, parameters=None, commit_tx=False, settings=None):
        started = time.perf_counter()
        if isinstance(query, str) and isinstance(parameters, dict) and parameters:
            prefixed, param_types = _normalize_parameters(parameters)
            typed_query = ydb.DataQuery(_build_query_with_declares(query, param_types), param_types)
            result = original_sync(self, typed_query, parameters=prefixed, commit_tx=commit_tx, settings=settings)
        else:
            result = original_sync(self, query, parameters=parameters, commit_tx=commit_tx, settings=settings)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms > 300:
            logger.warning("slow_ydb_query_ms=%.2f", elapsed_ms)
        return result

    @wraps(original_async)
    async def patched_async(self, query, parameters=None, commit_tx=False, settings=None):
        started = time.perf_counter()
        try:
            if isinstance(query, str) and isinstance(parameters, dict) and parameters:
                prefixed, param_types = _normalize_parameters(parameters)
                typed_query = ydb.DataQuery(_build_query_with_declares(query, param_types), param_types)
                return await original_async(self, typed_query, parameters=prefixed, commit_tx=commit_tx, settings=settings)
            return await original_async(self, query, parameters=parameters, commit_tx=commit_tx, settings=settings)
        finally:
            elapsed = time.perf_counter() - started
            await _ydb_latency_metrics.observe(elapsed)
            elapsed_ms = elapsed * 1000
            if elapsed_ms > 300:
                logger.warning("slow_ydb_query_ms=%.2f", elapsed_ms)

    ydb.table.TxContext.execute = patched_sync
    ydb.aio.table.TxContext.execute = patched_async
    _tx_execute_patched = True


install_ydb_execute_parameter_patch()


def _is_schema_limit_error(exc: Exception) -> bool:
    """Определяет ошибку лимита schema-операций YDB."""
    message = str(exc).lower()
    return (
        "number of schema operations" in message
        or "request exceeded a limit on the number of schema operations" in message
        or "server_code: 400080" in message
    )


def _is_table_missing_error(exc: Exception, table_name: str) -> bool:
    """Определяет ошибку отсутствующей таблицы YDB по имени таблицы."""
    message = str(exc).lower()
    table_name = table_name.lower()
    return (
        "cannot find table" in message
        and table_name in message
    )


def _build_credentials() -> ydb.Credentials:
    """Подбирает стратегию авторизации для YDB и логирует выбранный путь."""
    service_account_key_file = os.getenv("YDB_SERVICE_ACCOUNT_KEY_FILE_CREDENTIALS") or os.getenv("SA_KEY_FILE")
    if service_account_key_file:
        logger.info("YDB auth: service account key file from env: %s", service_account_key_file)
        return ydb.iam.ServiceAccountCredentials.from_file(service_account_key_file)

    service_account_key_content = os.getenv("YDB_SERVICE_ACCOUNT_KEY_CONTENT_CREDENTIALS") or os.getenv("SA_KEY_CONTENT")
    if service_account_key_content:
        logger.info("YDB auth: service account key content from env")
        raw_key = service_account_key_content.strip()

        # Частый случай в CI/CD: ключ положили как JSON-строку с экранированием.
        if raw_key.startswith('"') and raw_key.endswith('"'):
            try:
                raw_key = json.loads(raw_key)
            except json.JSONDecodeError:
                pass

        # Частый случай: в переменную попал repr(dict) c одинарными кавычками.
        if raw_key.startswith("{'") and raw_key.endswith("'}"):
            try:
                raw_key = json.dumps(ast.literal_eval(raw_key), ensure_ascii=False)
            except (ValueError, SyntaxError):
                pass

        # Ещё один частый формат: base64 от JSON.
        if not raw_key.startswith("{"):
            try:
                decoded = base64.b64decode(raw_key).decode("utf-8")
                if decoded.strip().startswith("{"):
                    raw_key = decoded
            except Exception:
                pass

        return ydb.iam.ServiceAccountCredentials.from_content(raw_key)

    runs_in_cloud_function = any(
        os.getenv(var_name)
        for var_name in ("FUNCTION_NAME", "FUNCTION_ID", "YC_FUNCTION_NAME", "YC_FUNCTION_ID")
    )
    if runs_in_cloud_function:
        logger.info("YDB auth: cloud function metadata credentials")
        return ydb.iam.MetadataUrlCredentials()

    if os.getenv("YDB_METADATA_CREDENTIALS", "0") == "1":
        logger.info("YDB auth: forced metadata credentials by YDB_METADATA_CREDENTIALS=1")
        return ydb.iam.MetadataUrlCredentials()

    logger.info("YDB auth: instance metadata service account token")
    return ydb.iam.MetadataUrlCredentials()


async def get_driver():
    """Возвращает инициализированный драйвер YDB."""
    global _driver
    if _driver is None:
        if not YDB_ENDPOINT or not YDB_DATABASE:
            raise ValueError("YDB_ENDPOINT и YDB_DATABASE должны быть явно заданы в переменных окружения.")        
        driver_config = ydb.DriverConfig(
            YDB_ENDPOINT,
            YDB_DATABASE,
            credentials=_build_credentials(),
            root_certificates=ydb.load_ydb_root_certificate(),
        )
        _driver = ydb.aio.Driver(driver_config)
        try:
            await _driver.wait(timeout=15)
        except TimeoutError:
            logger.error("Connect failed to YDB")
            logger.error("Last reported errors by discovery:")
            logger.error(_driver.discovery_debug_details())
            raise
    return _driver


async def get_pool():
    """Возвращает пул сессий YDB."""
    global _pool
    if _pool is None:
        driver = await get_driver()
        _pool = ydb.aio.SessionPool(driver, size=YDB_SESSION_POOL_SIZE)
        logger.info("YDB session pool initialized with size=%s", YDB_SESSION_POOL_SIZE)
    return _pool


async def init_db():
    """Создаёт таблицы при первом запуске."""
    pool = await get_pool()

    create_statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id Int64 NOT NULL,
            username Utf8,
            notification_settings Utf8 DEFAULT 'all',
            stats_count Int64 DEFAULT 0,
            birth_date Utf8,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id Int64 NOT NULL,
            title Utf8 NOT NULL,
            description Utf8,
            date_time Utf8 NOT NULL,
            duration_minutes Int64,
            period_end Utf8,
            location Utf8,
            price_total Double,
            price_per_person Double,
            participant_limit Int64,
            thread_id Int64,
            message_id Int64,
            creator_id Int64,
            responsible_id Int64,
            weather_info Utf8,
            carpool_enabled Bool DEFAULT false,
            status Utf8 DEFAULT 'active',
            category Utf8,
            created_at Timestamp,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS participants (
            id Int64 NOT NULL,
            event_id Int64 NOT NULL,
            user_id Int64 NOT NULL,
            status Utf8,
            car_seats Int64,
            passenger_of Int64,
            joined_at Timestamp,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reminder_jobs (
            id Int64 NOT NULL,
            event_id Int64 NOT NULL,
            interval_seconds Int64,
            scheduled_time Timestamp,
            sent Bool DEFAULT false,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forum_topics (
            id Int64 NOT NULL,
            message_thread_id Int64 NOT NULL,
            name Utf8 NOT NULL,
            is_closed Bool DEFAULT false,
            is_hidden Bool DEFAULT false,
            discovered_at Timestamp,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_category_subscriptions (
            user_id Int64 NOT NULL,
            category Utf8 NOT NULL,
            created_at Timestamp,
            PRIMARY KEY (user_id, category)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS random_meeting_opt_in (
            user_id Int64 NOT NULL,
            is_enabled Bool NOT NULL,
            updated_at Timestamp,
            PRIMARY KEY (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pending_users (
            user_id Int64 NOT NULL,
            username Utf8,
            full_name Utf8,
            status Utf8,
            created_at Timestamp,
            PRIMARY KEY (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fsm_states (
            bot_id Int64 NOT NULL,
            chat_id Int64 NOT NULL,
            user_id Int64 NOT NULL,
            thread_id Int64,
            business_connection_id Utf8,
            destiny Utf8 NOT NULL,
            state Utf8,
            data_json Utf8,
            updated_at Timestamp,
            PRIMARY KEY (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS approved_members (
            user_id Int64 NOT NULL,
            username Utf8,
            full_name Utf8,
            join_date Timestamp,
            intro_status Utf8 DEFAULT 'pending',
            PRIMARY KEY (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS command_usage_daily (
            usage_date Utf8 NOT NULL,
            role Utf8 NOT NULL,
            command Utf8 NOT NULL,
            usage_count Int64 NOT NULL,
            PRIMARY KEY (usage_date, role, command)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_events (
            id Int64 NOT NULL,
            group_id Int64 NOT NULL,
            organizer_id Int64 NOT NULL,
            title Utf8,
            total_amount Double NOT NULL,
            transfer_target_type Utf8,
            transfer_target_value Utf8,
            transfer_bank Utf8,
            transfer_bank_custom Utf8,
            transfer_recipient_name Utf8,
            status Utf8 NOT NULL,
            source_event_id Int64,
            thread_id Int64,
            message_id Int64,
            created_at Timestamp,
            closed_at Timestamp,
            PRIMARY KEY (id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS split_bill_participants (
            split_id Int64 NOT NULL,
            user_id Int64 NOT NULL,
            is_paid Bool NOT NULL,
            share_amount Double NOT NULL,
            joined_at Timestamp,
            PRIMARY KEY (split_id, user_id)
        )
        """,        
    ]

    schema_limit_hit = False
    for statement in create_statements:
        try:
            await pool.retry_operation(
                lambda session, sql=statement: session.execute_scheme(sql)
            )
        except Exception as exc:
            if _is_schema_limit_error(exc):
                schema_limit_hit = True
                logger.warning(
                    "Пропускаем schema init из-за лимита операций YDB: %s",
                    exc,
                )
                break
            raise

    if schema_limit_hit:
        logger.warning(
            "Инициализация схемы выполнена частично из-за лимита YDB; "
            "бот продолжит работу, повторите миграцию позже."
        )
    else:
        logger.info("Таблицы YDB созданы или уже существуют")


    # Мягкие миграции для уже существующих инсталляций.
    event_alters = [("responsible_id", "Int64"), ("period_end", "Utf8")]
    for column_name, column_type in event_alters:
        try:
            await pool.retry_operation(
                lambda session, name=column_name, ctype=column_type: session.execute_scheme(
                    f"""
                    ALTER TABLE events
                    ADD COLUMN {name} {ctype};
                    """
                )
            )
            logger.info("Добавлена колонка events.%s", column_name)
        except Exception as exc:
            if _is_schema_limit_error(exc):
                logger.warning("Пропускаем ALTER events.%s из-за лимита YDB: %s", column_name, exc)
            elif "path does not exist" in str(exc).lower():
                logger.warning("Таблица events пока недоступна для ALTER, миграция будет повторена позже")
            elif "already exists" in str(exc).lower():
                pass
            else:
                logger.warning("Не удалось применить мягкую миграцию events.%s: %s", column_name, exc)


    # Мягкая миграция split_bill_events по колонкам.
    # В старых инсталляциях часть колонок уже может быть создана, поэтому ALTER выполняем отдельно.
    split_bill_event_alters = [
        ("title", "Utf8"),
        ("transfer_target_type", "Utf8"),
        ("transfer_target_value", "Utf8"),
        ("transfer_bank", "Utf8"),
        ("transfer_bank_custom", "Utf8"),
        ("transfer_recipient_name", "Utf8"),
        ("thread_id", "Int64"),
        ("message_id", "Int64"),
    ]
    for column_name, column_type in split_bill_event_alters:
        try:
            await pool.retry_operation(
                lambda session, name=column_name, ctype=column_type: session.execute_scheme(
                    f"""
                    ALTER TABLE split_bill_events
                    ADD COLUMN {name} {ctype};
                    """
                )
            )
            logger.info("Добавлена колонка split_bill_events.%s", column_name)
        except Exception as exc:
            if _is_schema_limit_error(exc):
                logger.warning("Пропускаем ALTER split_bill_events.%s из-за лимита YDB: %s", column_name, exc)
                continue
            exc_text = str(exc).lower()
            if "path does not exist" in exc_text:
                logger.warning("Таблица split_bill_events пока недоступна для ALTER, миграция будет повторена позже")
                break
            if "already exists" in exc_text:
                continue
            logger.warning("Не удалось применить мягкую миграцию split_bill_events.%s: %s", column_name, exc)


async def get_or_create_user(user_id: int, username: str = None) -> int:
    """Возвращает пользователя из БД, создаёт если нет."""
    pool = await get_pool()

    # Проверяем, существует ли пользователь
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT id FROM users WHERE id = $user_id
            """,
            parameters={
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    if not result[0].rows:
        # Создаем нового пользователя
        await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                INSERT INTO users (id, username) VALUES ($user_id, $username)
                """,
                parameters={
                    "user_id": user_id,
                    "username": username or "",
                },
                commit_tx=True,
            )
        )

    return user_id


async def get_user_id_by_username(username: str) -> int | None:
    """Ищет user_id по username в approved_members/users."""
    normalized = (username or "").strip().lstrip("@").lower()
    if not normalized:
        return None

    pool = await get_pool()

    async def _query(session):
        query = """
        DECLARE $username AS Utf8;

        $uname = CAST($username AS Utf8);

        SELECT user_id
        FROM approved_members
        WHERE LOWER(COALESCE(username, "")) = $uname
        LIMIT 1;
        """
        rows = await session.transaction().execute(query, {"$username": normalized}, commit_tx=True)
        return rows[0].rows if rows else []

    try:
        rows = await pool.retry_operation_async(_query)
        if rows:
            return int(rows[0].user_id)
    except Exception:
        logger.exception("get_user_id_by_username failed in approved_members")

    async def _query_users(session):
        query = """
        DECLARE $username AS Utf8;

        $uname = CAST($username AS Utf8);

        SELECT id
        FROM users
        WHERE LOWER(COALESCE(username, "")) = $uname
        LIMIT 1;
        """
        rows = await session.transaction().execute(query, {"$username": normalized}, commit_tx=True)
        return rows[0].rows if rows else []

    try:
        rows = await pool.retry_operation_async(_query_users)
        if rows:
            return int(rows[0].id)
    except Exception:
        logger.exception("get_user_id_by_username failed in users")

    return None


async def add_pending_user(user_id: int, username: str | None, full_name: str | None) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO pending_users (user_id, username, full_name, status)
            VALUES ($user_id, $username, $full_name, $status)
            """,
            parameters={
                "user_id": int(user_id),
                "username": username or "",
                "full_name": full_name or "",
                "status": "waiting_approval",
            },
            commit_tx=True,
        )
    )


async def get_pending_user(user_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id, username, full_name, status, created_at
            FROM pending_users
            WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)},
            commit_tx=True,
        )
    )
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def delete_pending_user(user_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM pending_users WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)},
            commit_tx=True,
        )
    )


async def is_member_approved(user_id: int) -> bool:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id FROM approved_members WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)},
            commit_tx=True,
        )
    )
    return bool(result[0].rows)


async def approve_pending_user(user_id: int) -> Optional[Dict[str, Any]]:
    pending = await get_pending_user(user_id)
    if not pending:
        return None
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO approved_members (user_id, username, full_name, intro_status)
            VALUES ($user_id, $username, $full_name, $intro_status)
            """,
            parameters={
                "user_id": int(user_id),
                "username": str(pending.get("username") or ""),
                "full_name": str(pending.get("full_name") or ""),
                "intro_status": "pending",
            },
            commit_tx=True,
        )
    )
    await delete_pending_user(user_id)
    return pending


async def upsert_approved_member(
    user_id: int,
    username: str | None,
    full_name: str | None,
    *,
    intro_status: str = "completed",
) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO approved_members (user_id, username, full_name, intro_status)
            VALUES ($user_id, $username, $full_name, $intro_status)
            """,
            parameters={
                "user_id": int(user_id),
                "username": str(username or ""),
                "full_name": str(full_name or ""),
                "intro_status": intro_status,
            },
            commit_tx=True,
        )
    )


async def delete_approved_member(user_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM approved_members
            WHERE user_id = $user_id
            """,
            parameters={"user_id": int(user_id)},
            commit_tx=True,
        )
    )


async def record_command_usage(role: str, command: str, usage_date: str | None = None) -> None:
    pool = await get_pool()
    day = usage_date or datetime.utcnow().date().isoformat()
    try:
        prev = await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                SELECT usage_count
                FROM command_usage_daily
                WHERE usage_date = $usage_date AND role = $role AND command = $command
                """,
                parameters={"usage_date": day, "role": role, "command": command},
                commit_tx=True,
            )
        )
        current = int(prev[0].rows[0].usage_count) if prev and prev[0].rows else 0
        await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                UPSERT INTO command_usage_daily (usage_date, role, command, usage_count)
                VALUES ($usage_date, $role, $command, $usage_count)
                """,
                parameters={"usage_date": day, "role": role, "command": command, "usage_count": current + 1},
                commit_tx=True,
            )
        )
    except Exception as exc:
        if _is_table_missing_error(exc, "command_usage_daily"):
            logger.warning("Skip command usage stats: table command_usage_daily is missing: %s", exc)
            return
        raise


async def get_command_usage_summary(days: int = 7) -> list[dict[str, Any]]:
    pool = await get_pool()
    cutoff = (datetime.utcnow().date() - timedelta(days=max(0, days - 1))).isoformat()
    try:
        result = await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                SELECT role, SUM(usage_count) AS total_commands, COUNT(DISTINCT usage_date) AS active_days
                FROM command_usage_daily
                WHERE usage_date >= $cutoff
                GROUP BY role
                ORDER BY total_commands DESC
                """,
                parameters={"cutoff": cutoff},
                commit_tx=True,
            )
        )
    except Exception as exc:
        if _is_table_missing_error(exc, "command_usage_daily"):
            logger.warning("Cannot build command usage summary: table command_usage_daily is missing: %s", exc)
            return []
        raise
    items: list[dict[str, Any]] = []
    for row in result[0].rows if result else []:
        total = int(row.total_commands or 0)
        active_days = max(1, int(row.active_days or 1))
        items.append(
            {
                "role": str(row.role),
                "total_commands": total,
                "active_days": active_days,
                "avg_per_day": round(total / active_days, 2),
            }
        )
    return items


async def get_pending_intro_members() -> list[Dict[str, Any]]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id, username, full_name, join_date, intro_status
            FROM approved_members
            WHERE intro_status = 'pending'
            ORDER BY join_date
            """,
            commit_tx=True,
        )
    )
    return [_normalize_row(row) for row in result[0].rows]


async def get_intro_members_statuses() -> list[Dict[str, Any]]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id, username, full_name, join_date, intro_status
            FROM approved_members
            ORDER BY join_date
            """,
            commit_tx=True,
        )
    )
    return [_normalize_row(row) for row in result[0].rows]


async def get_approved_member_ids() -> list[int]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id
            FROM approved_members
            """,
            commit_tx=True,
        )
    )
    return [int(row.user_id) for row in (result[0].rows if result else [])]


async def update_intro_status(user_id: int, intro_status: str) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE approved_members SET intro_status = $intro_status
            WHERE user_id = $user_id
            """,
            parameters={
                "user_id": int(user_id),
                "intro_status": intro_status,
            },
            commit_tx=True,
        )
    )


async def get_member_reengage_candidates(days_inactive: int = 30) -> list[Dict[str, Any]]:
    """Возвращает одобренных участников с датой последнего участия в прошедших мероприятиях."""
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT
                am.user_id AS user_id,
                am.username AS username,
                am.full_name AS full_name,
                am.join_date AS join_date,
                MAX(e.date_time) AS last_event_date
            FROM approved_members AS am
            LEFT JOIN participants AS p ON p.user_id = am.user_id
            LEFT JOIN events AS e ON e.id = p.event_id
            GROUP BY am.user_id, am.username, am.full_name, am.join_date
            """,
            commit_tx=True,
        )
    )

    now = datetime.now(timezone.utc)
    items: list[Dict[str, Any]] = []
    for row in result[0].rows:
        record = _normalize_row(row)
        last_event_date = _parse_event_datetime(record.get("last_event_date"))
        if last_event_date is not None:
            if last_event_date.tzinfo is None:
                last_event_date = last_event_date.replace(tzinfo=timezone.utc)
            if last_event_date > now:
                continue
            inactive_days = (now - last_event_date).days
        else:
            join_date = _parse_event_datetime(record.get("join_date"))
            if join_date is not None and join_date.tzinfo is None:
                join_date = join_date.replace(tzinfo=timezone.utc)
            baseline = join_date or now
            inactive_days = (now - baseline).days

        if inactive_days < days_inactive:
            continue
        record["inactive_days"] = inactive_days
        record["last_event_date"] = last_event_date.isoformat() if last_event_date else None
        items.append(record)

    items.sort(key=lambda x: int(x.get("inactive_days", 0)), reverse=True)
    return items


async def create_event(event_data: Dict[str, Any]) -> int:
    """Создаёт мероприятие и возвращает его ID."""
    pool = await get_pool()

    # Генерируем ID для мероприятия
    import time

    event_id = int(time.time() * 1000)  # Используем timestamp в миллисекундах

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            INSERT INTO events (
                id, title, description, date_time, duration_minutes, period_end,
                location,
                price_total, price_per_person, participant_limit,
                thread_id, message_id, creator_id,
                responsible_id, weather_info, carpool_enabled, category
            ) VALUES (
                $id, $title, $description, $date_time, $duration_minutes, $period_end,
                $location,
                $price_total, $price_per_person, $participant_limit,
                $thread_id, $message_id, $creator_id,
                $responsible_id, $weather_info, $carpool_enabled, $category
            )
            """,
            parameters={
                "id": event_id,
                "title": event_data.get("title", ""),
                "description": event_data.get("description", ""),
                "date_time": event_data.get("date_time", ""),
                "duration_minutes": event_data.get("duration_minutes") or 0,
                "period_end": event_data.get("period_end") or "",
                "location": event_data.get("location", ""),
                "price_total": event_data.get("price_total") or 0.0,
                "price_per_person": event_data.get("price_per_person") or 0.0,
                "participant_limit": event_data.get("participant_limit") or 0,
                "thread_id": event_data.get("thread_id") or 0,
                "message_id": event_data.get("message_id") or 0,
                "creator_id": event_data.get("creator_id", 0),
                "responsible_id": event_data.get("responsible_id") or event_data.get("creator_id", 0),
                "weather_info": event_data.get("weather_info", ""),
                "carpool_enabled": bool(event_data.get("carpool_enabled", False)),
                "category": event_data.get("category", ""),
            },
            commit_tx=True,
        )
    )

    return event_id


async def get_event(event_id: int) -> Optional[Dict]:
    """Возвращает мероприятие по ID."""
    pool = await get_pool()

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT * FROM events WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )

    if not result[0].rows:
        return None

    row = result[0].rows[0]
    return _normalize_row(row)


async def update_event_message_id(event_id: int, thread_id: int, message_id: int):
    """Сохраняет thread_id и message_id после публикации."""
    pool = await get_pool()

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE events SET thread_id = $thread_id, message_id = $message_id 
            WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
                "thread_id": thread_id or 0,
                "message_id": message_id,
            },
            commit_tx=True,
        )
    )


async def get_active_events() -> List[Dict]:
    """Возвращает все активные мероприятия."""
    pool = await get_pool()

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            ORDER BY date_time
            """,
            commit_tx=True,
        )
    )

    return [_normalize_row(row) for row in result[0].rows]


def _normalize_row(row) -> Dict[str, Any]:
    """Преобразует строку YDB в обычный словарь python-типов."""
    event_dict: Dict[str, Any] = {}
    if isinstance(row, dict):
        row_items = row.items()
    elif hasattr(row, "items"):
        row_items = row.items()
    elif hasattr(row, "__fields__"):
        row_items = ((column, getattr(row, column)) for column in row.__fields__)
    elif hasattr(row, "_asdict"):
        row_items = row._asdict().items()
    else:
        row_items = ((column, getattr(row, column)) for column in dir(row) if not column.startswith("_"))

    for column, value in row_items:
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        event_dict[column] = value
    return event_dict


def _period_to_days(period: str, default_days: int = 7) -> int:
    return {
        "week": 7,
        "month": 30,
        "all": 365 * 10,
    }.get(period, default_days)


def _parse_event_datetime(value: Any) -> Optional[datetime]:
    """Пытается распарсить дату события из строки/объекта datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


async def add_participant(
    event_id: int,
    user_id: int,
    status: str = "going",
    car_seats: int = None,
    passenger_of: int = None,
) -> bool:
    """Добавляет участника в событие."""
    pool = await get_pool()

    # Проверяем, не существует ли уже участник
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT id FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    if result[0].rows:
        return False

    # Генерируем ID для участника
    import time

    participant_id = int(time.time() * 1000) + user_id  # Уникальный ID

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            INSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, $status, $car_seats, $passenger_of)
            """,
            parameters={
                "id": participant_id,
                "event_id": event_id,
                "user_id": user_id,
                "status": status,
                "car_seats": car_seats or 0,
                "passenger_of": passenger_of or 0,
            },
            commit_tx=True,
        )
    )

    return True


async def remove_participant(event_id: int, user_id: int):
    """Удаляет участника из события (и пассажиров если водитель)."""
    pool = await get_pool()

    # Получаем статус участника
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT status FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    if result[0].rows:
        status = result[0].rows[0].status
        if status == "driver":
            # Удаляем всех пассажиров этого водителя
            await pool.retry_operation(
                lambda session: session.transaction().execute(
                    """
                    DELETE FROM participants 
                    WHERE event_id = $event_id AND passenger_of = $driver_id
                    """,
                    parameters={
                        "event_id": event_id,
                        "driver_id": user_id,
                    },
                    commit_tx=True,
                )
            )

    # Удаляем самого участника
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM participants 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )


async def get_participants(event_id: int, status: str = None) -> List[int]:
    """Возвращает список ID участников с указанным статусом."""
    pool = await get_pool()

    if status:
        query = """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id AND status = $status
        """
        params = {
            "event_id": event_id,
            "status": status,
        }
    else:
        query = """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id
        """
        params = {
            "event_id": event_id,
        }

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            query,
            parameters=params,
            commit_tx=True,
        )
    )

    return [row.user_id for row in result[0].rows]


async def get_main_participants(event_id: int) -> List[int]:
    """Возвращает ID участников основного состава (идут + карпулинг)."""
    pool = await get_pool()

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT DISTINCT user_id FROM participants 
            WHERE event_id = $event_id AND status IN ('going', 'driver', 'passenger')
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )

    return [row.user_id for row in result[0].rows]


async def cancel_event(event_id: int) -> None:
    """Помечает мероприятие как отменённое и очищает участников."""
    pool = await get_pool()

    # Помечаем мероприятие как отменённое
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE events SET status = 'cancelled' WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )

    # Удаляем всех участников
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM participants WHERE event_id = $event_id
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )


async def get_user_stats(user_id: int) -> Dict:
    """⚠️ НОВОЕ: Возвращает статистику пользователя."""
    pool = await get_pool()

    # Получаем количество мероприятий, где пользователь был организатором
    result_creator = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(*) as events_count FROM events 
            WHERE creator_id = $user_id AND status = 'active'
            """,
            parameters={
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    events_count = (
        result_creator[0].rows[0].events_count if result_creator[0].rows else 0
    )

    # Получаем общее количество участий
    result_participations = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(DISTINCT event_id) as total_participations FROM participants 
            WHERE user_id = $user_id
            """,
            parameters={
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    total_participations = (
        result_participations[0].rows[0].total_participations
        if result_participations[0].rows
        else 0
    )

    return {
        "events_count": events_count,
        "total_participations": total_participations,
    }


async def get_admin_report_metrics() -> Dict[str, Any]:
    """Возвращает агрегированные метрики для команды /admin_report."""
    pool = await get_pool()

    active_events_result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(*) AS active_events
            FROM events
            WHERE status = 'active'
            """,
            commit_tx=True,
        )
    )
    active_events = (
        int(active_events_result[0].rows[0].active_events)
        if active_events_result and active_events_result[0].rows
        else 0
    )

    attendance_result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(*) AS attendance_count
            FROM events e
            JOIN participants p ON e.id = p.event_id
            WHERE e.status = 'active'
              AND p.status IN ('going', 'driver', 'passenger')
            """,
            commit_tx=True,
        )
    )
    attendance_count = (
        int(attendance_result[0].rows[0].attendance_count)
        if attendance_result and attendance_result[0].rows
        else 0
    )
    avg_attendance = round(attendance_count / active_events, 2) if active_events else 0.0

    no_show_result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(*) AS no_show
            FROM participants
            WHERE status = 'no_show'
            """,
            commit_tx=True,
        )
    )
    no_show = (
        int(no_show_result[0].rows[0].no_show)
        if no_show_result and no_show_result[0].rows
        else 0
    )

    top_categories_result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT category, COUNT(*) AS cnt
            FROM events
            WHERE status = 'active'
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 5
            """,
            commit_tx=True,
        )
    )

    top_categories: List[Dict[str, Any]] = []
    for row in top_categories_result[0].rows if top_categories_result else []:
        category_name = (row.category or 'Без категории').strip() if isinstance(row.category, str) else 'Без категории'
        top_categories.append({'category': category_name, 'cnt': int(row.cnt)})

    return {
        'active_events': active_events,
        'avg_attendance': avg_attendance,
        'no_show': no_show,
        'top_categories': top_categories,
    }


async def get_top_participants(days: int = 30, limit: int = 3) -> List[Dict]:
    """Топ участников по количеству участий за период."""
    pool = await get_pool()
    safe_days = max(0, int(days))
    cutoff_ts = datetime.utcnow() - timedelta(days=safe_days)

    # Получаем топ участников за последние N дней
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT 
                p.user_id,
                u.username,
                COUNT(DISTINCT p.event_id) as participation_count
            FROM participants p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.joined_at >= $cutoff_ts
            GROUP BY p.user_id, u.username
            ORDER BY participation_count DESC
            LIMIT $limit
            """,
            parameters={
                "cutoff_ts": cutoff_ts,
                "limit": int(limit),
            },
            commit_tx=True,
        )
    )

    top_participants = []
    for row in result[0].rows:
        top_participants.append(
            {
                "user_id": row.user_id,
                "username": row.username or f"User {row.user_id}",
                "participations": int(row.participation_count or 0),
            }
        )

    return top_participants


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
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COALESCE(MAX(id), 0) + 1 AS new_id FROM split_bill_events
            """,
            commit_tx=True,
        )
    )
    split_id = int(result[0].rows[0].new_id)

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO split_bill_events
            (id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, created_at)
            VALUES ($id, $group_id, $organizer_id, $title, $total_amount, $transfer_target_type, $transfer_target_value, $transfer_bank, $transfer_bank_custom, $transfer_recipient_name, $status, $source_event_id, $created_at)
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
            commit_tx=True,
        )
    )
    return split_id


async def get_split_bill(split_id: int) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT id, group_id, organizer_id, title, total_amount, transfer_target_type, transfer_target_value, transfer_bank, transfer_bank_custom, transfer_recipient_name, status, source_event_id, thread_id, message_id, created_at, closed_at
            FROM split_bill_events
            WHERE id = $split_id
            """,
            parameters={"split_id": int(split_id)},
            commit_tx=True,
        )
    )
    if not result[0].rows:
        return None
    return _normalize_row(result[0].rows[0])


async def update_split_bill_message_id(split_id: int, thread_id: int | None, message_id: int) -> None:
    """Сохраняет id опубликованной split-bill карточки для последующих refresh-обновлений."""
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
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
            commit_tx=True,
        )
    )


async def get_event_participant_ids(event_id: int) -> list[int]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT DISTINCT user_id FROM participants WHERE event_id = $event_id
            """,
            parameters={"event_id": int(event_id)},
            commit_tx=True,
        )
    )
    return [int(row.user_id) for row in result[0].rows]


async def get_split_bill_participants(split_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id, is_paid, share_amount, joined_at
            FROM split_bill_participants
            WHERE split_id = $split_id
            ORDER BY joined_at
            """,
            parameters={"split_id": int(split_id)},
            commit_tx=True,
        )
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
    pool = await get_pool()
    for participant in participants:
        await pool.retry_operation(
            lambda session, uid=int(participant["user_id"]): session.transaction().execute(
                """
                UPDATE split_bill_participants
                SET share_amount = $share_amount
                WHERE split_id = $split_id AND user_id = $user_id
                """,
                parameters={"split_id": int(split_id), "user_id": uid, "share_amount": share},
                commit_tx=True,
            )
        )


async def add_split_bill_participant(split_id: int, user_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO split_bill_participants (split_id, user_id, is_paid, share_amount, joined_at)
            VALUES ($split_id, $user_id, false, 0.0, $joined_at)
            """,
            parameters={
                "split_id": int(split_id),
                "user_id": int(user_id),
                "joined_at": datetime.utcnow(),
            },
            commit_tx=True,
        )
    )
    await recalculate_split_bill_shares(split_id)


async def remove_split_bill_participant(split_id: int, user_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM split_bill_participants WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={"split_id": int(split_id), "user_id": int(user_id)},
            commit_tx=True,
        )
    )
    await recalculate_split_bill_shares(split_id)


async def mark_split_bill_paid(split_id: int, user_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE split_bill_participants
            SET is_paid = true
            WHERE split_id = $split_id AND user_id = $user_id
            """,
            parameters={"split_id": int(split_id), "user_id": int(user_id)},
            commit_tx=True,
        )
    )


async def close_split_bill(split_id: int) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE split_bill_events
            SET status = 'closed', closed_at = $closed_at
            WHERE id = $split_id
            """,
            parameters={"split_id": int(split_id), "closed_at": datetime.utcnow()},
            commit_tx=True,
        )
    )

    
async def find_events(query: str, period: str = "month", limit: int = 20) -> List[Dict]:
    """Поиск предстоящих активных мероприятий по названию/месту/категории."""
    pool = await get_pool()

    period_days = _period_to_days(period, default_days=30)
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            AND (
                title LIKE '%' || $query || '%' 
                OR location LIKE '%' || $query || '%'
                OR category LIKE '%' || $query || '%'
                OR description LIKE '%' || $query || '%'
            )
            ORDER BY date_time
            """,
            parameters={
                "query": query,
            },
            commit_tx=True,
        )
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    events: List[Dict] = []

    for row in result[0].rows:
        event_dict = _normalize_row(row)
        event_dt = _parse_event_datetime(event_dict.get("date_time"))
        if event_dt is None:
            continue
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        if now <= event_dt <= max_dt:
            events.append(event_dict)

    events.sort(key=lambda x: x.get("date_time", ""))
    return events[:limit]


async def get_user_events(user_id: int, status: str = None) -> List[Dict]:
    """Возвращает мероприятия пользователя: как участника и/или организатора."""
    pool = await get_pool()

    if status == "organizer":
        # Мероприятия, где пользователь организатор
        query = """
            SELECT e.* FROM events e
            WHERE e.creator_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    elif status == "participant":
        # Мероприятия, где пользователь участник
        query = """
            SELECT DISTINCT e.* FROM events e
            JOIN participants p ON e.id = p.event_id
            WHERE p.user_id = $user_id AND e.status = 'active'
            ORDER BY e.date_time
        """
        params = {"user_id": user_id}
    else:
        # Все мероприятия пользователя (и как организатор, и как участник)
        query = """
            SELECT * FROM events
            WHERE (
                creator_id = $user_id
                OR id IN (
                    SELECT event_id FROM participants
                    WHERE user_id = $user_id
                )
            ) 
            AND status = 'active'
            ORDER BY date_time
        """
        params = {"user_id": user_id}

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            query,
            parameters=params,
            commit_tx=True,
        )
    )

    return [_normalize_row(row) for row in result[0].rows]


async def move_from_waitlist(event_id: int) -> Optional[int]:
    """Перемещает первого из резерва в основной список."""
    pool = await get_pool()

    event = await get_event(event_id)
    if not event:
        return None

    participant_limit = event.get("participant_limit") or 0
    if participant_limit > 0:
        going = await get_main_participants(event_id)
        if len(going) >= participant_limit:
            return None
        
    # Получаем первого участника из резерва
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id FROM participants 
            WHERE event_id = $event_id AND status = 'waitlist'
            ORDER BY joined_at
            LIMIT 1
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )

    if not result[0].rows:
        return None

    user_id = result[0].rows[0].user_id

    # Обновляем статус на 'going'
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE participants 
            SET status = 'going' 
            WHERE event_id = $event_id AND user_id = $user_id
            """,
            parameters={
                "event_id": event_id,
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    return user_id


async def get_drivers_with_passengers(event_id: int) -> List[Dict]:
    """Возвращает список водителей с их пассажирами."""
    pool = await get_pool()

    # Получаем всех водителей
    result_drivers = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT user_id, car_seats FROM participants 
            WHERE event_id = $event_id AND status = 'driver'
            """,
            parameters={
                "event_id": event_id,
            },
            commit_tx=True,
        )
    )

    drivers = []
    for row in result_drivers[0].rows:
        driver_id = row.user_id
        car_seats = row.car_seats

        # Получаем пассажиров этого водителя
        result_passengers = await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                SELECT user_id FROM participants 
                WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
                """,
                parameters={
                    "event_id": event_id,
                    "driver_id": driver_id,
                },
                commit_tx=True,
            )
        )

        passengers = [
            row_passenger.user_id for row_passenger in result_passengers[0].rows
        ]

        drivers.append(
            {
                "user_id": driver_id,
                "car_seats": car_seats,
                "passengers": passengers,
            }
        )

    return drivers


async def get_driver_free_seats(driver_id: int, event_id: int) -> int:
    """Возвращает количество свободных мест у водителя."""
    pool = await get_pool()

    # Получаем информацию о водителе
    result_driver = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT car_seats FROM participants 
            WHERE event_id = $event_id AND user_id = $driver_id AND status = 'driver'
            """,
            parameters={
                "event_id": event_id,
                "driver_id": driver_id,
            },
            commit_tx=True,
        )
    )

    if not result_driver[0].rows:
        return 0

    car_seats = result_driver[0].rows[0].car_seats

    # Получаем количество пассажиров
    result_passengers = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT COUNT(*) as passenger_count FROM participants 
            WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
            """,
            parameters={
                "event_id": event_id,
                "driver_id": driver_id,
            },
            commit_tx=True,
        )
    )

    passenger_count = (
        result_passengers[0].rows[0].passenger_count if result_passengers[0].rows else 0
    )

    # Свободные места = общие места - пассажиры - 1 (сам водитель)
    free_seats = car_seats - passenger_count - 1
    return max(0, free_seats)


async def set_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Атомарно назначает пользователя водителем, обновляя существующую запись участника."""
    pool = await get_pool()

    participant_id = int(time.time() * 1000) + int(user_id)

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id;

            UPSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, 'driver', $car_seats, 0);
            """,
            parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "car_seats": int(car_seats),
            },
            commit_tx=True,
        )
    )
    return True


async def set_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Атомарно назначает пользователя пассажиром выбранного водителя."""
    free_seats = await get_driver_free_seats(driver_id, event_id)
    if free_seats <= 0:
        return False
    pool = await get_pool()
    participant_id = int(time.time() * 1000) + int(user_id)
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM participants
            WHERE event_id = $event_id AND user_id = $user_id;

            UPSERT INTO participants (id, event_id, user_id, status, car_seats, passenger_of)
            VALUES ($id, $event_id, $user_id, 'passenger', 0, $driver_id);
            """,
            parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "driver_id": int(driver_id),
            },
            commit_tx=True,
        )
    )
    return True


async def add_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Добавляет или обновляет водителя."""
    return await set_driver(event_id, user_id, car_seats)

async def add_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Добавляет или обновляет пассажира к водителю."""
    return await set_passenger(event_id, user_id, driver_id)


async def get_forum_topics_raw(bot, chat_id: int):
    """
    Возвращает список тем форума из локального хранилища.

    Telegram Bot API не предоставляет стабильного кросс-версийного метода для
    прямого листинга всех тем, поэтому используем обнаруженные/сохранённые темы.
    """
    try:
        chat = await bot.get_chat(chat_id)

        if not getattr(chat, "is_forum", False):
            return []

        stored_topics = await get_all_topics()
        return [
            {
                "message_thread_id": row.get("message_thread_id"),
                "name": row.get("name", f"Тема {row.get('message_thread_id')}"),
                "is_closed": bool(row.get("is_closed", False)),
                "is_hidden": bool(row.get("is_hidden", False)),
            }
            for row in stored_topics
        ]
    except (TypeError, ValueError) as e:
        logger.error("Ошибка при получении тем форума: %s", e)
        return await get_all_topics()


async def save_forum_topic(message_thread_id: int, name: str) -> bool:
    pool = await get_pool()
    topic_id = int(message_thread_id)
    topic_name = name or f"Тема {message_thread_id}"
    
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO forum_topics (id, message_thread_id, name, is_closed, is_hidden)
            VALUES ($id, $message_thread_id, $name, false, false)
            """,
            parameters={
                "id": topic_id,
                "message_thread_id": topic_id,
                "name": topic_name,
            },
            commit_tx=True,
        )
    )
    return True


async def get_all_topics() -> List[Dict]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT message_thread_id, name, is_closed, is_hidden
            FROM forum_topics
            ORDER BY message_thread_id
            """,
            commit_tx=True,
        )
    )
    return [
        {
            "message_thread_id": row.message_thread_id,
            "name": row.name,
            "is_closed": bool(row.is_closed),
            "is_hidden": bool(row.is_hidden),
        }
        for row in result[0].rows
    ]


async def get_topic_by_id(message_thread_id: int) -> Optional[Dict]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT message_thread_id, name, is_closed, is_hidden
            FROM forum_topics
            WHERE message_thread_id = $message_thread_id
            LIMIT 1
            """,
            parameters={"message_thread_id": int(message_thread_id)},
            commit_tx=True,
        )
    )
    if not result[0].rows:
        return None
    row = result[0].rows[0]
    return {
        "message_thread_id": row.message_thread_id,
        "name": row.name,
        "is_closed": bool(row.is_closed),
        "is_hidden": bool(row.is_hidden),
    }


async def get_topic_name_by_thread_id(message_thread_id: int | None) -> Optional[str]:
    """Возвращает название темы по её thread_id."""
    if message_thread_id in (None, 0):
        return None
    topic = await get_topic_by_id(int(message_thread_id))
    if not topic:
        return None
    return topic.get("name")


async def sync_topics_from_config() -> int:
    import asyncio

    try:
        from bot.topics_config import TOPICS_MAPPING
    except Exception:
        return 0

    if not TOPICS_MAPPING:
        return 0

    await asyncio.gather(
        *(save_forum_topic(int(thread_id), str(name)) for thread_id, name in TOPICS_MAPPING.items())
    )
    return len(TOPICS_MAPPING)


async def set_random_meeting_opt_in(user_id: int, is_enabled: bool) -> None:
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPSERT INTO random_meeting_opt_in (user_id, is_enabled)
            VALUES ($user_id, $is_enabled)
            """,
            parameters={"user_id": int(user_id), "is_enabled": bool(is_enabled)},
            commit_tx=True,
        )
    )


async def get_random_meeting_opt_in_users() -> list[int]:
    pool = await get_pool()
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT r.user_id AS user_id
            FROM random_meeting_opt_in AS r
            INNER JOIN approved_members AS am ON am.user_id = r.user_id
            WHERE r.is_enabled = true
            ORDER BY r.user_id
            """,
            commit_tx=True,
        )
    )
    return [row.user_id for row in result[0].rows]


async def update_event_status(event_id: int, status: str):
    """Обновляет статус мероприятия."""
    pool = await get_pool()

    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE events SET status = $status WHERE id = $event_id
            """,
            parameters={
                "event_id": event_id,
                "status": status,
            },
            commit_tx=True,
        )
    )


async def set_event_responsible(event_id: int, responsible_id: int) -> None:
    """Назначает ответственного за мероприятие."""
    pool = await get_pool()
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            UPDATE events
            SET responsible_id = $responsible_id
            WHERE id = $event_id
            """,
            parameters={
                "event_id": int(event_id),
                "responsible_id": int(responsible_id),
            },
            commit_tx=True,
        )
    )
    

async def get_events_for_digest(period: str = "week") -> List[Dict]:
    """Получение предстоящих активных мероприятий для дайджеста."""
    pool = await get_pool()

    period_days = _period_to_days(period)
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            ORDER BY date_time
            """,
            commit_tx=True,
        )
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    events: List[Dict] = []
    for row in result[0].rows:
        event_dict = _normalize_row(row)
        event_dt = _parse_event_datetime(event_dict.get("date_time"))
        if event_dt is None:
            continue
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        if now <= event_dt <= max_dt:
            events.append(event_dict)

    event_ids = {int(event["id"]) for event in events}
    if event_ids:
        counts_result = await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                SELECT event_id, status FROM participants
                """,
                commit_tx=True,
            )
        )
        counts: dict[int, dict[str, int]] = {event_id: {"going": 0, "waitlist": 0} for event_id in event_ids}
        for row in counts_result[0].rows:
            if not hasattr(row, "event_id"):
                continue
            event_id = int(row.event_id)
            if event_id not in counts:
                continue
            status = str(row.status)
            if status in {"going", "driver", "passenger"}:
                counts[event_id]["going"] += 1
            elif status == "waitlist":
                counts[event_id]["waitlist"] += 1
        for event in events:
            event_counts = counts.get(int(event["id"]), {})
            event["going_count"] = event_counts.get("going", 0)
            event["waitlist_count"] = event_counts.get("waitlist", 0)

    events.sort(key=lambda x: x.get("date_time", ""))
    return events


async def set_user_category_subscriptions(user_id: int, categories: list[str]) -> None:
    """Перезаписывает список подписок пользователя по категориям."""
    pool = await get_pool()

    # Удаляем существующие подписки пользователя
    await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            DELETE FROM user_category_subscriptions WHERE user_id = $user_id
            """,
            parameters={
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    # Добавляем новые подписки
    for category in categories:
        if category.strip():  # Пропускаем пустые категории
            await pool.retry_operation(
                lambda session: session.transaction().execute(
                    """
                    INSERT INTO user_category_subscriptions (user_id, category)
                    VALUES ($user_id, $category)
                    """,
                    parameters={
                        "user_id": user_id,
                        "category": category.strip(),
                    },
                    commit_tx=True,
                )
            )

    logger.info(f"Обновлены подписки пользователя {user_id}: {categories}")


async def get_user_category_subscriptions(user_id: int) -> list[str]:
    """Возвращает категории, на которые подписан пользователь."""
    pool = await get_pool()

    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT category FROM user_category_subscriptions 
            WHERE user_id = $user_id 
            ORDER BY category
            """,
            parameters={
                "user_id": user_id,
            },
            commit_tx=True,
        )
    )

    return [row.category for row in result[0].rows]


async def get_events_for_user_subscriptions(
    user_id: int, period: str = "week"
) -> List[Dict]:
    """Возвращает активные события, которые совпадают с подписками пользователя."""
    pool = await get_pool()

    # Получаем подписки пользователя
    subscriptions = await get_user_category_subscriptions(user_id)
    if not subscriptions:
        return []

    period_days = _period_to_days(period)
    result = await pool.retry_operation(
        lambda session: session.transaction().execute(
            """
            SELECT * FROM events 
            WHERE status = 'active' 
            ORDER BY date_time
            """,
            commit_tx=True,
        )
    )

    now = datetime.now(timezone.utc)
    max_dt = now + timedelta(days=period_days)
    subscriptions_set = {
        item.strip().lower() for item in subscriptions if item and item.strip()
    }
    events: List[Dict] = []

    for row in result[0].rows:
        event_dict = _normalize_row(row)
        event_category = str(event_dict.get("category") or "").strip().lower()
        if event_category not in subscriptions_set:
            continue
        event_dt = _parse_event_datetime(event_dict.get("date_time"))
        if event_dt is None:
            continue
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        if now <= event_dt <= max_dt:
            events.append(event_dict)

    event_ids = {int(event["id"]) for event in events}
    if event_ids:
        counts_result = await pool.retry_operation(
            lambda session: session.transaction().execute(
                """
                SELECT event_id, status FROM participants
                """,
                commit_tx=True,
            )
        )
        counts: dict[int, dict[str, int]] = {event_id: {"going": 0, "waitlist": 0} for event_id in event_ids}
        for row in counts_result[0].rows:
            if not hasattr(row, "event_id"):
                continue
            event_id = int(row.event_id)
            if event_id not in counts:
                continue
            status = str(row.status)
            if status in {"going", "driver", "passenger"}:
                counts[event_id]["going"] += 1
            elif status == "waitlist":
                counts[event_id]["waitlist"] += 1
        for event in events:
            event_counts = counts.get(int(event["id"]), {})
            event["going_count"] = event_counts.get("going", 0)
            event["waitlist_count"] = event_counts.get("waitlist", 0)
            
    events.sort(key=lambda x: x.get("date_time", ""))
    return events
