import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

from bot.utils.metrics import LatencyMetrics, Timer

logger = logging.getLogger(__name__)

_update_latency = LatencyMetrics(name="update_processing", window_size=2000, log_every=100)


async def get_update_latency_snapshot() -> dict[str, float | int | str]:
    return await _update_latency.snapshot()


class UpdateLatencyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        timer = Timer()
        try:
            return await handler(event, data)
        finally:
            await _update_latency.observe(timer.elapsed())
