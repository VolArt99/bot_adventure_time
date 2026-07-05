"""Shared database helpers."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from bot.db_pool import execute, fetch

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
        self.rows = [
            record if isinstance(record, _CompatRow) else _CompatRow(record)
            for record in records
        ]


async def _run_query(query: str, parameters: dict | None = None):
    import sys

    legacy = sys.modules.get("bot.database_pg")
    if legacy is not None:
        patched = getattr(legacy, "_run_query", None)
        if patched is not None and patched is not _run_query:
            return await patched(query, parameters)

    records = await fetch(query, parameters)
    return [_CompatResultSet(records)]


async def _run_execute(query: str, parameters: dict | None = None) -> None:
    import sys

    legacy = sys.modules.get("bot.database_pg")
    if legacy is not None:
        patched = getattr(legacy, "_run_execute", None)
        if patched is not None and patched is not _run_execute:
            await patched(query, parameters)
            return

    await execute(query, parameters)


def _normalize_row(row) -> Dict[str, Any]:
    """Convert a DB row to a plain Python dict."""
    while hasattr(row, "_record") and not isinstance(row, dict):
        row = row._record
    if isinstance(row, dict):
        row_items = row.items()
    elif hasattr(row, "items") and callable(row.items):
        row_items = row.items()
    else:
        row_items = ((column, row[column]) for column in row.keys())

    event_dict: Dict[str, Any] = {}
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


def _event_matches_period_filter(
    event_dict: Dict, now: datetime, max_dt: datetime
) -> bool:
    """Проверяет, попадает ли активное мероприятие в выбранный период дайджеста/афиши."""
    event_dt = _parse_event_datetime(event_dict.get("date_time"))
    if event_dt is None:
        return False
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)

    period_end_dt = _parse_event_datetime(event_dict.get("period_end"))
    if period_end_dt and period_end_dt.tzinfo is None:
        period_end_dt = period_end_dt.replace(tzinfo=timezone.utc)

    if period_end_dt and period_end_dt > event_dt:
        if period_end_dt < now:
            return False
        if event_dt <= now:
            return True
        return event_dt <= max_dt

    return now <= event_dt <= max_dt
