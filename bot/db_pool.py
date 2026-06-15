"""Async PostgreSQL connection pool and query helpers."""

from __future__ import annotations

import os
import re
import time
from typing import Any

import asyncpg

from bot.utils.metrics import LatencyMetrics

_PARAM_RE = re.compile(r"\$(\w+)")

_pool: asyncpg.Pool | None = None
_pg_latency_metrics = LatencyMetrics(name="pg_query", window_size=5000, log_every=200)

DATABASE_URL = os.getenv("DATABASE_URL")
DB_POOL_MIN_SIZE = max(1, int(os.getenv("DB_POOL_MIN_SIZE", "1")))
DB_POOL_MAX_SIZE = max(DB_POOL_MIN_SIZE, int(os.getenv("DB_POOL_MAX_SIZE", "5")))


def _resolve_database_url() -> str:
    url = (DATABASE_URL or "").strip()
    if url:
        return url

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", "bot")
    password = os.getenv("PGPASSWORD", "")
    database = os.getenv("PGDATABASE", "adventure_time")
    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


def prepare_query(query: str, parameters: dict[str, Any] | None) -> tuple[str, list[Any]]:
    """Convert `$name` placeholders to asyncpg positional `$1`, `$2`, ..."""
    if not parameters:
        return query, []

    ordered_names: list[str] = []
    seen: set[str] = set()
    for match in _PARAM_RE.finditer(query):
        name = match.group(1)
        if name.isdigit():
            continue
        if name in parameters and name not in seen:
            seen.add(name)
            ordered_names.append(name)

    index_by_name = {name: index + 1 for index, name in enumerate(ordered_names)}

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.isdigit():
            return match.group(0)
        if name in index_by_name:
            return f"${index_by_name[name]}"
        return match.group(0)

    converted = _PARAM_RE.sub(_replace, query)
    values = [parameters[name] for name in ordered_names]
    return converted, values


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        database_url = _resolve_database_url()
        if not database_url:
            raise ValueError(
                "DATABASE_URL (or PGHOST/PGUSER/PGPASSWORD/PGDATABASE) must be set."
            )
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def execute(query: str, parameters: dict[str, Any] | None = None) -> str:
    pool = await get_pool()
    sql, values = prepare_query(query, parameters)
    started = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            return await conn.execute(sql, *values)
    finally:
        elapsed = time.perf_counter() - started
        await _pg_latency_metrics.observe(elapsed)
        elapsed_ms = elapsed * 1000
        if elapsed_ms > 300:
            import logging

            logging.getLogger(__name__).warning("slow_pg_query_ms=%.2f", elapsed_ms)


async def fetch(query: str, parameters: dict[str, Any] | None = None) -> list[asyncpg.Record]:
    pool = await get_pool()
    sql, values = prepare_query(query, parameters)
    started = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            return await conn.fetch(sql, *values)
    finally:
        elapsed = time.perf_counter() - started
        await _pg_latency_metrics.observe(elapsed)


async def fetchrow(query: str, parameters: dict[str, Any] | None = None) -> asyncpg.Record | None:
    pool = await get_pool()
    sql, values = prepare_query(query, parameters)
    started = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow(sql, *values)
    finally:
        elapsed = time.perf_counter() - started
        await _pg_latency_metrics.observe(elapsed)


async def fetchval(query: str, parameters: dict[str, Any] | None = None) -> Any:
    pool = await get_pool()
    sql, values = prepare_query(query, parameters)
    started = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(sql, *values)
    finally:
        elapsed = time.perf_counter() - started
        await _pg_latency_metrics.observe(elapsed)
