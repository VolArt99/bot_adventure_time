# точка входа, инициализация бота, диспетчера, планировщика

import asyncio
import logging
import traceback
from html import escape
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.fsm.strategy import FSMStrategy

from bot.config import BOT_TOKEN, validate_runtime_config
from bot.database import init_db, sync_topics_from_config
import bot.handlers.common_feature.handlers as common
import bot.handlers.events as events
import bot.handlers.participation as participation
import bot.handlers.digest as digest
import bot.handlers.my_events as my_events
import bot.handlers.roadmap as roadmap
import bot.handlers.subscriptions as subscriptions
import bot.handlers.admin as admin
import bot.handlers.split_bill_feature.handlers as split_bill
from bot.utils.scheduler import restore_jobs, start_scheduler, schedule_digest
from bot.fsm_storage_pg import PgStorage
from bot.config import GROUP_ID
from bot.init_flags import should_run_schema_init
from bot.utils.helpers import build_owner_contact_html
from bot.utils.telegram_errors import is_benign_telegram_error

from aiogram.types import BotCommand, BotCommandScopeDefault, Update
from bot.commands import COMMAND_SPECS

USER_COMMANDS = [
    BotCommand(command=spec.command, description=spec.description.split(".", 1)[0])
    for spec in COMMAND_SPECS
    if spec.group != "admin"
]


async def setup_bot_commands() -> None:
    """Публикует команды в системном меню Telegram."""
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = PgStorage()

dp = Dispatcher(storage=storage, fsm_strategy=FSMStrategy.GLOBAL_USER)
_is_initialized = False
_polling_initialized = False
_init_lock = asyncio.Lock()
_owner_error_throttle: dict[str, datetime] = {}
ERROR_THROTTLE_SECONDS = 300


async def _notify_owner_about_error(event: Update | None, exc: Exception) -> None:
    from bot.config import OWNER_ID
    if OWNER_ID <= 0:
        return

    err_key = f"{type(exc).__name__}:{str(exc)[:120]}"
    now = datetime.now(timezone.utc)
    last_sent = _owner_error_throttle.get(err_key)
    if last_sent and (now - last_sent).total_seconds() < ERROR_THROTTLE_SECONDS:
        return
    _owner_error_throttle[err_key] = now

    update_id = escape(str(getattr(event, "update_id", "unknown")))
    user_id = None
    user_command = "unknown"
    if event and event.message and event.message.from_user:
        user_id = event.message.from_user.id
        user_command = (event.message.text or "").strip()[:120] or "unknown"
    elif event and event.callback_query and event.callback_query.from_user:
        user_id = event.callback_query.from_user.id
        user_command = (event.callback_query.data or "").strip()[:120] or "unknown"

    safe_user_id = escape(str(user_id or "unknown"))
    safe_user_command = escape(user_command)
    tb_short = "\n".join(traceback.format_exception_only(type(exc), exc)).strip()
    safe_tb_short = escape(tb_short[:800])
    text = (
        "🚨 <b>Техническая ошибка бота</b>\n"
        f"• update_id: <code>{update_id}</code>\n"
        f"• user_id: <code>{safe_user_id}</code>\n"
        f"• command: <code>{safe_user_command}</code>\n"
        f"• error: <code>{safe_tb_short}</code>\n"
        f"• throttle: {ERROR_THROTTLE_SECONDS}с"
    )
    try:
        await bot.send_message(OWNER_ID, text, parse_mode="HTML")
    except Exception:
        logger.exception("Не удалось отправить ошибку владельцу")


async def _notify_user_about_error(event: Update | None) -> None:
    if not event:
        return
    user_id = None
    if event.message and event.message.from_user:
        user_id = event.message.from_user.id
    elif event.callback_query and event.callback_query.from_user:
        user_id = event.callback_query.from_user.id
    if not user_id:
        return
    from bot.config import OWNER_CONTACT, OWNER_ID

    owner_contact = build_owner_contact_html(OWNER_CONTACT or "@Vol_Artem", OWNER_ID)
    text = (
        "❌ Команда не сработала. Пожалуйста, обратитесь в поддержку к владельцу группы. "
        f"Свяжитесь с админом {owner_contact}."
    )
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramForbiddenError:
        logger.info("Не удалось уведомить пользователя об ошибке: user_id=%s заблокировал бота", user_id)
    except Exception:
        logger.exception("Не удалось уведомить пользователя об ошибке")


def _register_handlers() -> None:
    """Регистрирует роутеры и middleware один раз."""

    from bot.middleware.command_access import CommandAccessMiddleware

    access_middleware = CommandAccessMiddleware()
    dp.message.middleware(access_middleware)
    dp.callback_query.middleware(access_middleware)

    dp.include_router(common.router)
    dp.include_router(events.router)
    dp.include_router(participation.router)
    dp.include_router(digest.router)
    dp.include_router(my_events.router)
    dp.include_router(roadmap.router)
    dp.include_router(subscriptions.router)
    dp.include_router(split_bill.router)
    dp.include_router(admin.router)

    from bot.middleware.topic_discoverer import TopicDiscovererMiddleware
    from bot.middleware.latency_metrics import UpdateLatencyMiddleware

    dp.update.middleware(UpdateLatencyMiddleware())
    dp.update.middleware(TopicDiscovererMiddleware())

    @dp.errors()
    async def on_global_error(event, exception=None):
        err = exception or getattr(event, "exception", None)
        if err and is_benign_telegram_error(err):
            logger.info(
                "Benign Telegram error while processing update: %s",
                err,
            )
            return True
        logger.exception("Unhandled error while processing update", exc_info=err)
        update_obj = getattr(event, "update", None) if event else None
        await _notify_owner_about_error(update_obj, err or Exception("unknown error"))
        await _notify_user_about_error(update_obj)
        return True
    
    
async def ensure_initialized(*, for_polling: bool = False) -> None:
    """Ленивая инициализация перед запуском long polling."""
    global _is_initialized, _polling_initialized

    if _is_initialized and (not for_polling or _polling_initialized):
        return

    async with _init_lock:
        if _is_initialized and (not for_polling or _polling_initialized):
            return

        if not _is_initialized:
            logger.info("Инициализация бота...")
            validate_runtime_config()
            if should_run_schema_init():
                await init_db()
                logger.info("Схема БД проверена/инициализирована")
            else:
                logger.info("AUTO_INIT_DB disabled: пропускаем init_db() в этом окружении")
            await asyncio.gather(sync_topics_from_config(), setup_bot_commands())
            _register_handlers()
            logger.info("База, темы и роутеры инициализированы")
            _is_initialized = True

        # Планировщик нужен только для long-running polling режима.
        if for_polling and not _polling_initialized:
            start_scheduler()
            await restore_jobs(bot)
            if GROUP_ID:
                await schedule_digest(bot, GROUP_ID)
            from bot.utils.health import start_heartbeat
            from bot.utils.monitoring import schedule_monitoring

            start_heartbeat()
            schedule_monitoring(bot)
            logger.info("Планировщик, напоминания, weekly digest, heartbeat и мониторинг восстановлены")
            _polling_initialized = True

async def _on_shutdown() -> None:
    from bot.db_pool import close_pool
    from bot.utils.scheduler import scheduler
    from bot.utils.health import stop_heartbeat

    await stop_heartbeat()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен")
    await close_pool()
    logger.info("Пул PostgreSQL закрыт")


async def main():
    logger.info("Запуск бота...")
    await ensure_initialized(for_polling=True)
    dp.shutdown.register(_on_shutdown)

    # Polling несовместим с активным webhook (остаток старого деплоя / BotFather).
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook снят, режим polling")

    # Запуск поллинга с повторными попытками при сетевых сбоях
    logger.info("Запуск поллинга...")
    retry_delay = 5
    max_retry_delay = 60
    while True:
        try:
            await dp.start_polling(bot)
            break
        except TelegramNetworkError as e:
            logger.error(
                f"Ошибка сети при запуске/работе поллинга: {e}. "
                f"Повтор через {retry_delay} сек."
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")