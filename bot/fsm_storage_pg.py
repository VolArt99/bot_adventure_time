"""FSM storage for aiogram backed by PostgreSQL."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from bot.db_pool import execute, fetchrow

logger = logging.getLogger(__name__)


class PgStorage(BaseStorage):
    """Persist FSM state/data in PostgreSQL table `fsm_states`."""

    @staticmethod
    def _as_int(value: Any, *, default: int | None = None) -> int | None:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _key_parameters(cls, key: StorageKey | Mapping[str, Any] | Any) -> dict[str, Any]:
        raw_key = key if isinstance(key, Mapping) else vars(key) if hasattr(key, "__dict__") else {
            "bot_id": getattr(key, "bot_id", None),
            "chat_id": getattr(key, "chat_id", None),
            "user_id": getattr(key, "user_id", None),
            "thread_id": getattr(key, "thread_id", None),
            "business_connection_id": getattr(key, "business_connection_id", None),
            "destiny": getattr(key, "destiny", None),
        }
        thread_id = cls._as_int(raw_key.get("thread_id"), default=0)
        business_connection_id = raw_key.get("business_connection_id") or ""
        params = {
            "bot_id": cls._as_int(raw_key.get("bot_id"), default=0),
            "chat_id": cls._as_int(raw_key.get("chat_id"), default=0),
            "user_id": cls._as_int(raw_key.get("user_id"), default=0),
            "thread_id": thread_id if thread_id is not None else 0,
            "business_connection_id": business_connection_id,
            "destiny": raw_key.get("destiny") or "default",
        }
        if raw_key.get("bot_id") != params["bot_id"]:
            logger.warning("FSM key bot_id normalized from %r to %r", raw_key.get("bot_id"), params["bot_id"])
        return params

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        params = {**self._key_parameters(key), "state": state_value}
        await execute(
            """
            INSERT INTO fsm_states (
                bot_id, chat_id, user_id, thread_id, business_connection_id, destiny, state, updated_at
            ) VALUES (
                $bot_id, $chat_id, $user_id, $thread_id, $business_connection_id, $destiny, $state, NOW()
            )
            ON CONFLICT (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
            DO UPDATE SET state = EXCLUDED.state, updated_at = NOW()
            """,
            parameters=params,
        )

    async def get_state(self, key: StorageKey) -> str | None:
        params = self._key_parameters(key)
        row = await fetchrow(
            """
            SELECT state FROM fsm_states
            WHERE bot_id = $bot_id
              AND chat_id = $chat_id
              AND user_id = $user_id
              AND thread_id = $thread_id
              AND business_connection_id = $business_connection_id
              AND destiny = $destiny
            """,
            parameters=params,
        )
        if row is None:
            return None
        return row["state"]

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        serialized = json.dumps(dict(data), ensure_ascii=False)
        params = {**self._key_parameters(key), "data_json": serialized}
        await execute(
            """
            INSERT INTO fsm_states (
                bot_id, chat_id, user_id, thread_id, business_connection_id, destiny, data_json, updated_at
            ) VALUES (
                $bot_id, $chat_id, $user_id, $thread_id, $business_connection_id, $destiny, $data_json, NOW()
            )
            ON CONFLICT (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
            DO UPDATE SET data_json = EXCLUDED.data_json, updated_at = NOW()
            """,
            parameters=params,
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        params = self._key_parameters(key)
        row = await fetchrow(
            """
            SELECT data_json FROM fsm_states
            WHERE bot_id = $bot_id
              AND chat_id = $chat_id
              AND user_id = $user_id
              AND thread_id = $thread_id
              AND business_connection_id = $business_connection_id
              AND destiny = $destiny
            """,
            parameters=params,
        )
        if row is None:
            return {}

        data_json = row["data_json"]
        if not data_json:
            return {}

        try:
            data = json.loads(data_json)
        except json.JSONDecodeError:
            return {}

        return data if isinstance(data, dict) else {}

    async def close(self) -> None:
        return None
