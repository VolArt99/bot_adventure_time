import logging
from typing import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import (
    ADMIN_DAILY_COMMAND_LIMIT,
    GROUP_ID,
    MEMBER_ALLOWED_COMMANDS,
    MEMBER_DAILY_COMMAND_LIMIT,
    OUTSIDER_ALLOWED_COMMANDS,
    OUTSIDER_START_DAILY_LIMIT,
)
from bot.database import (
    delete_approved_member,
    get_user_daily_command_count,
    increment_user_daily_command_count,
    is_member_approved,
    record_command_usage,
)
from bot.db.usage import usage_date_key
from bot.utils.roles import is_admin, is_owner
from bot.utils.telegram_errors import safe_callback_answer

logger = logging.getLogger(__name__)

OUTSIDER_FREE_CALLBACKS = frozenset(
    {"onboarding_start", "rules_ack", "menu_donate", "donate_back", "menu_home"}
)


class CommandAccessMiddleware(BaseMiddleware):
    """Роли и дневные лимиты для команд и callback в личных сообщениях."""

    @staticmethod
    def _extract_command(message: Message) -> str | None:
        text = message.text or ""
        if not text.startswith("/"):
            return None
        return text.split()[0].split("@")[0].lstrip("/").lower()

    @staticmethod
    def _today_key() -> str:
        return usage_date_key()

    @staticmethod
    async def _clear_active_scenario_if_needed(
        event: Message,
        state,
        command: str,
    ) -> None:
        if state is None:
            return

        current_state = await state.get_state()
        if not current_state:
            return

        restartable_commands = {"create_event", "split_bill"}
        if command in restartable_commands:
            return

        if current_state.startswith("CreateEvent:"):
            await state.clear()
            await event.answer("ℹ️ Предыдущий сценарий создания мероприятия остановлен.")
            return

        if current_state.startswith("SplitBillCreate:"):
            await state.clear()
            await event.answer("ℹ️ Предыдущий сценарий разделения чека остановлен.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable],
        event: TelegramObject,
        data: dict,
    ):
        if isinstance(event, Message):
            if event.chat.type != "private":
                return await handler(event, data)
            return await self._handle_private_message(handler, event, data)

        if isinstance(event, CallbackQuery):
            if not event.message or event.message.chat.type != "private":
                return await handler(event, data)
            return await self._handle_private_callback(handler, event, data)

        return await handler(event, data)

    async def _handle_private_message(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable],
        event: Message,
        data: dict,
    ):
        user = event.from_user
        if user is None:
            return await handler(event, data)

        command = self._extract_command(event)
        if not command:
            return await handler(event, data)

        await self._clear_active_scenario_if_needed(event, data.get("state"), command)
        return await self._authorize(
            handler,
            event,
            data,
            user_id=user.id,
            action=command,
            reply_target=event,
        )

    @staticmethod
    async def _is_wizard_navigation(state) -> bool:
        if state is None:
            return False
        current = await state.get_state()
        if not current:
            return False
        return current.startswith("CreateEvent:") or current.startswith("SplitBillCreate:")

    async def _handle_private_callback(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable],
        event: CallbackQuery,
        data: dict,
    ):
        user = event.from_user
        if user is None:
            return await handler(event, data)

        action = (event.data or "callback").strip()
        if action in OUTSIDER_FREE_CALLBACKS:
            return await handler(event, data)

        wizard_active = await self._is_wizard_navigation(data.get("state"))
        return await self._authorize(
            handler,
            event,
            data,
            user_id=user.id,
            action=f"cb:{action[:80]}",
            reply_target=event,
            is_callback=True,
            skip_daily_limit=wizard_active,
        )

    async def _authorize(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable],
        event: TelegramObject,
        data: dict,
        *,
        user_id: int,
        action: str,
        reply_target: Message | CallbackQuery,
        is_callback: bool = False,
        skip_daily_limit: bool = False,
    ):
        user_is_owner = is_owner(user_id)
        user_is_admin = is_admin(user_id)
        is_approved_member = await self._sync_membership(reply_target, user_id)

        if user_is_owner:
            await record_command_usage("owner", action)
            return await handler(event, data)

        if user_is_admin:
            return await self._apply_limit(
                handler,
                event,
                data,
                user_id=user_id,
                daily_limit=ADMIN_DAILY_COMMAND_LIMIT,
                role="admin",
                action=action,
                reply_target=reply_target,
                is_callback=is_callback,
                limit_text="⚠️ Дневной лимит команд для админа исчерпан. Попробуйте снова завтра.",
                skip_daily_limit=skip_daily_limit,
            )

        if is_approved_member:
            if not is_callback:
                command = action
                if command not in MEMBER_ALLOWED_COMMANDS:
                    logger.info(
                        "access_denied user_id=%s command=%s role=member reason=restricted_command",
                        user_id,
                        command,
                    )
                    await self._reply(reply_target, "❌ Эта команда доступна только админу или владельцу.")
                    return
            return await self._apply_limit(
                handler,
                event,
                data,
                user_id=user_id,
                daily_limit=MEMBER_DAILY_COMMAND_LIMIT,
                role="member",
                action=action,
                reply_target=reply_target,
                is_callback=is_callback,
                limit_text="⚠️ Дневной лимит команд исчерпан. Попробуйте снова завтра.",
                skip_daily_limit=skip_daily_limit,
            )

        if not is_callback:
            command = action
            if command not in OUTSIDER_ALLOWED_COMMANDS:
                logger.info(
                    "access_denied user_id=%s command=%s role=outsider reason=command_not_allowed",
                    user_id,
                    command,
                )
                await self._reply(
                    reply_target,
                    "❌ До подтверждения доступа вам доступна только команда /start.",
                )
                return

        return await self._apply_limit(
            handler,
            event,
            data,
            user_id=user_id,
            daily_limit=OUTSIDER_START_DAILY_LIMIT,
            role="outsider",
            action=action,
            reply_target=reply_target,
            is_callback=is_callback,
            limit_text="⚠️ Дневной лимит команд до одобрения исчерпан. Попробуйте снова завтра.",
            skip_daily_limit=skip_daily_limit,
        )

    async def _sync_membership(self, event: Message | CallbackQuery, user_id: int) -> bool:
        is_approved_member = await is_member_approved(user_id)
        if not hasattr(event, "bot") or GROUP_ID == 0:
            return is_approved_member
        try:
            member = await event.bot.get_chat_member(GROUP_ID, user_id)
            in_group = member.status in {"member", "administrator", "creator"}
        except (TelegramForbiddenError, TelegramBadRequest):
            in_group = False

        if is_approved_member and not in_group:
            await delete_approved_member(user_id)
            return False

        return is_approved_member

    async def _apply_limit(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable],
        event: TelegramObject,
        data: dict,
        *,
        user_id: int,
        daily_limit: int,
        role: str,
        action: str,
        reply_target: Message | CallbackQuery,
        is_callback: bool,
        limit_text: str,
        skip_daily_limit: bool = False,
    ):
        if skip_daily_limit:
            await record_command_usage(role, action)
            return await handler(event, data)

        today = self._today_key()
        current_usage = await get_user_daily_command_count(user_id, today)
        if current_usage >= daily_limit:
            await self._reply(reply_target, limit_text, is_callback=is_callback)
            return

        await increment_user_daily_command_count(user_id, today)
        await record_command_usage(role, action)
        return await handler(event, data)

    @staticmethod
    async def _reply(
        target: Message | CallbackQuery,
        text: str,
        *,
        is_callback: bool = False,
    ) -> None:
        try:
            if isinstance(target, CallbackQuery) or is_callback:
                await safe_callback_answer(target, text, show_alert=True)  # type: ignore[arg-type]
            else:
                await target.answer(text)
        except TelegramForbiddenError:
            logger.info("limit_reply_skipped reason=blocked")
