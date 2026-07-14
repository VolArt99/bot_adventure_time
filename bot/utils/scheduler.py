# настройка APScheduler, восстановление задач при старте

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from datetime import datetime, timedelta
import pytz
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.config import (
    TIMEZONE,
    REMINDER_INTERVALS,
    GROUP_ID,
    DIGEST_DAY_OF_WEEK,
    DIGEST_HOUR,
    ATTENDANCE_CONFIRM_SECONDS,
    ATTENDANCE_CONFIRM_HOURS,
)
from bot.database import (
    get_active_events,
    get_participants,
    get_event,
    get_main_participants,
    record_attendance_prompts,
)

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)

scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()}, timezone=TZ)

# Последние отправленные напоминания по мероприятию (для удаления при следующем)
_reminder_message_ids: dict[int, dict[str, int | dict[int, int]]] = {}


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Планировщик запущен")


async def schedule_attendance_for_event_data(event: dict, bot) -> None:
    """Планирует интерактивное подтверждение участия за 24ч до старта."""
    if not event or event["status"] != "active":
        return

    event_time = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    now = datetime.now(TZ)
    check_time = event_time - timedelta(seconds=ATTENDANCE_CONFIRM_SECONDS)
    if check_time <= now:
        return

    job_id = f"attendance_{event['id']}"
    scheduler.add_job(
        send_attendance_prompt,
        trigger="date",
        run_date=check_time,
        args=[event["id"], bot],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Запланировано подтверждение участия %s на %s", job_id, check_time)


async def send_attendance_prompt(event_id: int, bot) -> None:
    """Отправляет участникам запрос «всё ещё иду?» в ЛС."""
    try:
        event = await get_event(event_id)
        if not event or event["status"] != "active":
            return

        participants = await get_main_participants(event_id)
        if not participants:
            return

        await record_attendance_prompts(event_id, participants)

        from bot.texts import format_attendance_prompt_text
        from bot.keyboards import attendance_confirmation_keyboard
        from bot.utils.notifications import send_private_dm

        text = format_attendance_prompt_text(event, ATTENDANCE_CONFIRM_HOURS)
        keyboard = attendance_confirmation_keyboard(event_id)
        sent = 0
        for uid in participants:
            if await send_private_dm(bot, uid, text, reply_markup=keyboard):
                sent += 1

        logger.info(
            "Attendance prompt sent event_id=%s recipients=%s sent=%s",
            event_id,
            len(participants),
            sent,
        )
    except Exception as exc:
        logger.error("Ошибка отправки подтверждения участия event_id=%s: %s", event_id, exc)


async def schedule_reminders_for_event_data(event: dict, bot):
    """Планирует напоминания для уже загруженного мероприятия."""
    if not event or event["status"] != "active":
        return

    event_time = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    now = datetime.now(TZ)

    for interval in REMINDER_INTERVALS:
        if interval == ATTENDANCE_CONFIRM_SECONDS:
            continue
        remind_time = event_time - timedelta(seconds=interval)
        if remind_time > now:
            job_id = f"reminder_{event['id']}_{interval}"
            scheduler.add_job(
                send_reminder,
                trigger="date",
                run_date=remind_time,
                args=[event["id"], interval, bot],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Запланировано напоминание {job_id} на {remind_time}")

    await schedule_attendance_for_event_data(event, bot)


async def schedule_reminders_for_event(event_id: int, bot):
    """Планирует напоминания для мероприятия по id."""
    event = await get_event(event_id)
    await schedule_reminders_for_event_data(event, bot)


async def _delete_previous_reminders(bot, event_id: int) -> None:
    """Удаляет предыдущие напоминания по мероприятию, если они ещё доступны."""
    stored = _reminder_message_ids.pop(event_id, None)
    if not stored:
        return

    group_message_id = stored.get("group")
    if isinstance(group_message_id, int):
        try:
            await bot.delete_message(GROUP_ID, group_message_id)
        except TelegramBadRequest:
            pass

    dm_messages = stored.get("dm")
    if isinstance(dm_messages, dict):
        for user_id, message_id in dm_messages.items():
            try:
                await bot.delete_message(int(user_id), int(message_id))
            except (TelegramBadRequest, TelegramForbiddenError):
                pass


async def send_reminder(event_id: int, interval: int, bot):
    """Отправляет напоминание участникам."""
    try:
        event = await get_event(event_id)
        if not event or event["status"] != "active":
            return

        participants = await get_participants(event_id, "going")
        if not participants:
            return

        minutes_until = interval // 60

        from bot.texts import format_group_reminder_text, format_reminder_text
        from bot.utils.helpers import build_event_message_link
        from bot.utils.notifications import send_private_dm

        event_link = build_event_message_link(
            GROUP_ID,
            event.get("message_id"),
            event.get("thread_id"),
        )
        text = format_reminder_text(event, minutes_until, event_link=event_link)

        await _delete_previous_reminders(bot, event_id)

        dm_message_ids: dict[int, int] = {}
        for uid in participants:
            message_id = await send_private_dm(
                bot,
                uid,
                text,
                return_message_id=True,
            )
            if isinstance(message_id, int):
                dm_message_ids[uid] = message_id

        group_message_id: int | None = None
        if event.get("thread_id"):
            group_text = format_group_reminder_text(
                event["title"],
                minutes_until,
                event_link=event_link,
            )
            group_message = await bot.send_message(
                chat_id=GROUP_ID,
                message_thread_id=event["thread_id"],
                text=group_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            group_message_id = group_message.message_id

        if dm_message_ids or group_message_id is not None:
            _reminder_message_ids[event_id] = {
                "dm": dm_message_ids,
                "group": group_message_id,
            }

        logger.info(f"Напоминание отправлено для мероприятия {event_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")


async def restore_jobs(bot):
    """Восстанавливает напоминания при старте бота."""
    logger.info("Восстановление запланированных напоминаний...")
    events = await get_active_events()
    count = 0
    for event in events:
        await schedule_reminders_for_event_data(event, bot)
        count += 1
    logger.info(f"Восстановлено {count} мероприятий с напоминаниями")


async def schedule_digest(bot, chat_id: int, thread_id: int = None):
    """Планирует еженедельный дайджест."""
    from bot.handlers.digest import send_digest

    scheduler.add_job(
        send_digest,
        trigger="cron",
        day_of_week=max(0, DIGEST_DAY_OF_WEEK - 1),
        hour=DIGEST_HOUR,
        args=[bot, chat_id, thread_id],
        id="weekly_digest",
        replace_existing=True,
    )
    logger.info("Запланирован еженедельный дайджест")
