"""Periodic health/latency monitoring with optional owner alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot

from bot.config import MONITORING_INTERVAL_MINUTES, MONITORING_P95_ALERT_MS, OWNER_ID
from bot.database import get_active_events
from bot.db_pool import get_pg_latency_snapshot, get_pool
from bot.middleware.latency_metrics import get_update_latency_snapshot
from bot.utils.health import touch_heartbeat

logger = logging.getLogger(__name__)

_last_alert_at: datetime | None = None
_ALERT_COOLDOWN_SECONDS = max(300, MONITORING_INTERVAL_MINUTES * 60)


async def run_monitoring_check(bot: Bot) -> None:
    touch_heartbeat()

    update_metrics = await get_update_latency_snapshot()
    pg_metrics = await get_pg_latency_snapshot()
    active_events = len(await get_active_events())

    try:
        pool = await get_pool()
        pool_size = pool.get_size()
        pool_idle = pool.get_idle_size()
    except Exception:
        pool_size = -1
        pool_idle = -1

    logger.info(
        "monitoring_snapshot active_events=%s pool_size=%s pool_idle=%s "
        "update_p95_ms=%.2f pg_p95_ms=%.2f update_samples=%s pg_samples=%s",
        active_events,
        pool_size,
        pool_idle,
        float(update_metrics.get("p95_ms", 0)),
        float(pg_metrics.get("p95_ms", 0)),
        update_metrics.get("samples", 0),
        pg_metrics.get("samples", 0),
    )

    if OWNER_ID <= 0:
        return

    update_p95 = float(update_metrics.get("p95_ms", 0))
    pg_p95 = float(pg_metrics.get("p95_ms", 0))
    if update_p95 < MONITORING_P95_ALERT_MS and pg_p95 < MONITORING_P95_ALERT_MS:
        return

    global _last_alert_at
    now = datetime.now(timezone.utc)
    if _last_alert_at and (now - _last_alert_at).total_seconds() < _ALERT_COOLDOWN_SECONDS:
        return
    _last_alert_at = now

    text = (
        "⚠️ <b>Мониторинг: повышенная задержка</b>\n"
        f"• update p95: <code>{update_p95:.0f} ms</code> (порог {MONITORING_P95_ALERT_MS})\n"
        f"• pg p95: <code>{pg_p95:.0f} ms</code>\n"
        f"• активных событий: <b>{active_events}</b>\n"
        f"• pool: <code>{pool_idle}/{pool_size}</code> idle/size"
    )
    try:
        await bot.send_message(OWNER_ID, text, parse_mode="HTML")
    except Exception:
        logger.exception("monitoring_alert_failed owner_id=%s", OWNER_ID)


def schedule_monitoring(bot: Bot) -> None:
    from bot.utils.scheduler import scheduler

    scheduler.add_job(
        run_monitoring_check,
        trigger="interval",
        minutes=max(5, MONITORING_INTERVAL_MINUTES),
        args=[bot],
        id="monitoring_check",
        replace_existing=True,
    )
    logger.info("Monitoring job scheduled every %s minutes", MONITORING_INTERVAL_MINUTES)
