from aiogram.types import CallbackQuery

from bot.utils.callback_policy import CALLBACK_KEEP_PUBLIC_MESSAGE
from bot.utils.ui import is_private_message, safe_delete_bot_message


async def finalize_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    delete_message: bool = CALLBACK_KEEP_PUBLIC_MESSAGE,
    show_alert: bool = False,
) -> None:
    """Единая точка завершения callback: answer + policy-driven удаление сообщения бота.

    В публичных чатах сообщения сохраняются по явной политике ``delete_message``.
    В личных чатах предыдущая карточка бота удаляется при любом нажатии кнопки,
    чтобы диалог не засорялся устаревшими меню и промежуточными подсказками.
    """
    await callback.answer(text=text, show_alert=show_alert)
    if callback.message and (delete_message or is_private_message(callback.message)):
        await safe_delete_bot_message(callback.message)
