"""Process heartbeat for Docker healthcheck."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bot.config import BOT_HEARTBEAT_INTERVAL_SECONDS, BOT_HEARTBEAT_PATH

logger = logging.getLogger(__name__)

_heartbeat_task: asyncio.Task | None = None


def touch_heartbeat() -> None:
    path = Path(BOT_HEARTBEAT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


async def heartbeat_loop() -> None:
    while True:
        try:
            touch_heartbeat()
        except Exception:
            logger.exception("heartbeat_touch_failed path=%s", BOT_HEARTBEAT_PATH)
        await asyncio.sleep(max(10, BOT_HEARTBEAT_INTERVAL_SECONDS))


def start_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        return
    touch_heartbeat()
    _heartbeat_task = asyncio.create_task(heartbeat_loop())
    logger.info("Heartbeat started path=%s interval=%ss", BOT_HEARTBEAT_PATH, BOT_HEARTBEAT_INTERVAL_SECONDS)


async def stop_heartbeat() -> None:
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    _heartbeat_task = None
