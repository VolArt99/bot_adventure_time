from aiogram.types import CallbackQuery

from bot.utils.callback_policy import CALLBACK_KEEP_PUBLIC_MESSAGE
from bot.utils.telegram_errors import safe_callback_answer
from bot.utils.ui import safe_delete_bot_message


def parse_callback_suffix_int(data: str | None, *, prefix: str) -> int | None:
    """Парсит целое из callback.data после фиксированного префикса."""
    if not data or not data.startswith(prefix):
        return None
    suffix = data[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def parse_callback_split_int(
    data: str | None,
    *,
    index: int,
    min_parts: int | None = None,
    separator: str = "_",
) -> int | None:
    """Парсит целое из сегмента callback.data, разделённого separator."""
    if not data:
        return None
    parts = data.split(separator)
    if min_parts is not None and len(parts) < min_parts:
        return None
    if index < 0 or index >= len(parts):
        return None
    segment = parts[index]
    if not segment.isdigit():
        return None
    return int(segment)


async def finalize_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    delete_message: bool = CALLBACK_KEEP_PUBLIC_MESSAGE,
    show_alert: bool = False,
    skip_answer: bool = False,
) -> None:
    """Единая точка завершения callback: answer + policy-driven удаление сообщения бота.

    Сообщение с кнопками удаляется только по явной политике ``delete_message``.
    Это сохраняет редактируемые меню на месте, а wizard-сценарии продолжают
    убирать устаревшие шаговые карточки через ``CALLBACK_DELETE_WIZARD_MESSAGE``.

    ``skip_answer=True`` используйте, если callback уже подтверждён через ``ack_callback``
    или ``safe_callback_answer`` до тяжёлой логики.
    """
    if not skip_answer:
        await safe_callback_answer(callback, text=text, show_alert=show_alert)
    if callback.message and delete_message:
        await safe_delete_bot_message(callback.message)
