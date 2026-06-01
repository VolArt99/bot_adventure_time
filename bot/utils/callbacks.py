from aiogram.types import CallbackQuery

from bot.utils.callback_policy import CALLBACK_KEEP_PUBLIC_MESSAGE
from bot.utils.ui import safe_delete_bot_message


async def finalize_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    delete_message: bool = CALLBACK_KEEP_PUBLIC_MESSAGE,
    show_alert: bool = False,
) -> None:
    """Единая точка завершения callback: answer + policy-driven удаление сообщения бота.

    Сообщение с кнопками удаляется только по явной политике ``delete_message``.
    Это сохраняет редактируемые меню на месте, а wizard-сценарии продолжают
    убирать устаревшие шаговые карточки через ``CALLBACK_DELETE_WIZARD_MESSAGE``.
    """
    await callback.answer(text=text, show_alert=show_alert)
    if callback.message and delete_message:
        await safe_delete_bot_message(callback.message)
