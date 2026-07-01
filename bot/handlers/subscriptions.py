import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import GROUP_ID
from bot.constants import EVENT_CATEGORIES, EVENT_CATEGORY_GROUPS
from bot.database import (
    get_events_for_user_subscriptions,
    get_or_create_user,
    get_topic_name_by_thread_id,
    get_user_category_subscriptions,
    set_user_category_subscriptions,
)
from bot.keyboards import period_keyboard
from bot.texts import format_digest_text
from bot.utils.helpers import build_event_message_link, get_username_by_id
from bot.utils.callbacks import finalize_callback
from bot.utils.telegram_errors import ack_callback
from bot.utils.callback_policy import CALLBACK_DELETE_WIZARD_MESSAGE

router = Router(name=__name__)


def _subscriptions_keyboard(selected: list[str]):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    rows = []
    for group_key, group_data in EVENT_CATEGORY_GROUPS.items():
        total = len(group_data["subcategories"])
        selected_in_group = len([c for c in group_data["subcategories"] if c in selected])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{group_data['title']} ({selected_in_group}/{total})",
                    callback_data=f"sub_group_{group_key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="✅ Подписаться на всё", callback_data="sub_all")])
    rows.append([InlineKeyboardButton(text="🚫 Отписаться от всего", callback_data="sub_none")])
    rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="sub_save")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscriptions_group_keyboard(group_key: str, selected: list[str]):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    group = EVENT_CATEGORY_GROUPS[group_key]
    rows = []
    for category in group["subcategories"]:
        mark = "✅ " if category in selected else ""
        rows.append([InlineKeyboardButton(text=f"{mark}{category.title()}", callback_data=f"sub_toggle_{category}")])

    rows.append([InlineKeyboardButton(text="➕ Подписаться на всю группу", callback_data=f"sub_grp_all_{group_key}")])
    rows.append([InlineKeyboardButton(text="➖ Отписаться от всей группы", callback_data=f"sub_grp_none_{group_key}")])
    rows.append([InlineKeyboardButton(text="↩️ К группам", callback_data="sub_back")])
    rows.append([InlineKeyboardButton(text="✅ Подписаться на всё", callback_data="sub_all")])
    rows.append([InlineKeyboardButton(text="🚫 Отписаться от всего", callback_data="sub_none")])    
    rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="sub_save")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("subscriptions"))
async def cmd_subscriptions(message: Message):
    await get_or_create_user(message.from_user.id, message.from_user.username)
    selected = await get_user_category_subscriptions(message.from_user.id)
    await message.answer(
        "📬 Выберите группы категорий для персонального дайджеста:",
        reply_markup=_subscriptions_keyboard(selected),
    )


@router.callback_query(F.data.startswith("sub_group_"))
async def open_subscription_group(callback: CallbackQuery):
    group_key = callback.data.removeprefix("sub_group_")
    if group_key not in EVENT_CATEGORY_GROUPS:
        await finalize_callback(callback, "Группа не найдена", show_alert=True)
        return
    selected = await get_user_category_subscriptions(callback.from_user.id)
    await finalize_callback(callback)
    await callback.message.edit_reply_markup(
        reply_markup=_subscriptions_group_keyboard(group_key, selected)
    )


@router.callback_query(F.data.startswith("sub_toggle_"))
async def toggle_subscription(callback: CallbackQuery):
    category = callback.data.removeprefix("sub_toggle_")
    selected = await get_user_category_subscriptions(callback.from_user.id)

    if category in selected:
        selected.remove(category)
    else:
        selected.append(category)

    await set_user_category_subscriptions(callback.from_user.id, selected)
    await finalize_callback(callback, "Подписки обновлены")
    current = callback.message.reply_markup.inline_keyboard[0][0].callback_data
    if current and current.startswith("sub_toggle_"):
        category = current.removeprefix("sub_toggle_")
        group_key = next(
            (key for key, value in EVENT_CATEGORY_GROUPS.items() if category in value["subcategories"]),
            "other",
        )
        await callback.message.edit_reply_markup(reply_markup=_subscriptions_group_keyboard(group_key, sorted(set(selected))))
        return    
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_keyboard(sorted(set(selected))))


@router.callback_query(F.data.startswith("sub_grp_all_"))
async def subscribe_group_subcategories(callback: CallbackQuery):
    group_key = callback.data.removeprefix("sub_grp_all_")
    group = EVENT_CATEGORY_GROUPS.get(group_key)
    if not group:
        await finalize_callback(callback, "Группа не найдена", show_alert=True)
        return
    selected = set(await get_user_category_subscriptions(callback.from_user.id))
    selected.update(group["subcategories"])
    await set_user_category_subscriptions(callback.from_user.id, sorted(selected))
    await finalize_callback(callback, "Подгруппа подписана")
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_group_keyboard(group_key, sorted(selected)))


@router.callback_query(F.data.startswith("sub_grp_none_"))
async def unsubscribe_group_subcategories(callback: CallbackQuery):
    group_key = callback.data.removeprefix("sub_grp_none_")
    group = EVENT_CATEGORY_GROUPS.get(group_key)
    if not group:
        await finalize_callback(callback, "Группа не найдена", show_alert=True)
        return
    selected = set(await get_user_category_subscriptions(callback.from_user.id))
    selected.difference_update(group["subcategories"])
    await set_user_category_subscriptions(callback.from_user.id, sorted(selected))
    await finalize_callback(callback, "Подгруппа отписана")
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_group_keyboard(group_key, sorted(selected)))

    
@router.callback_query(F.data == "sub_back")
async def back_subscriptions(callback: CallbackQuery):
    selected = await get_user_category_subscriptions(callback.from_user.id)
    await finalize_callback(callback)
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_keyboard(selected))


@router.callback_query(F.data == "sub_all")
async def subscribe_all(callback: CallbackQuery):
    await set_user_category_subscriptions(callback.from_user.id, EVENT_CATEGORIES)
    await finalize_callback(callback, "✅ Включены все категории")
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_keyboard(EVENT_CATEGORIES))


@router.callback_query(F.data == "sub_none")
async def subscribe_none(callback: CallbackQuery):
    await set_user_category_subscriptions(callback.from_user.id, [])
    await finalize_callback(callback, "🚫 Все подписки отключены")
    await callback.message.edit_reply_markup(reply_markup=_subscriptions_keyboard([]))
    

@router.callback_query(F.data == "sub_save")
async def save_subscriptions(callback: CallbackQuery):
    selected = await get_user_category_subscriptions(callback.from_user.id)
    if selected:
        await callback.message.answer(f"✅ Подписки сохранены: {', '.join(selected)}")
    else:
        await callback.message.answer("✅ Подписки очищены. Персональный дайджест отключён.")
    await finalize_callback(callback, "Сохранено", delete_message=CALLBACK_DELETE_WIZARD_MESSAGE)


@router.message(Command("my_digest"))
async def cmd_my_digest(message: Message):
    await message.answer(
        "Выберите период для персонального дайджеста по вашим подпискам:",
        reply_markup=period_keyboard("my_digest"),
    )


@router.callback_query(F.data.startswith("my_digest_"))
async def my_digest_with_period(callback: CallbackQuery):
    await ack_callback(callback)
    period = callback.data.removeprefix("my_digest_")
    events = await get_events_for_user_subscriptions(callback.from_user.id, period=period)

    if not events:
        await callback.message.answer("По вашим подпискам пока нет мероприятий на выбранный период.")
        await finalize_callback(
            callback,
            delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
            skip_answer=True,
        )
        return

    creator_ids = sorted({event["creator_id"] for event in events})
    resolved_names, topic_names = await asyncio.gather(
        asyncio.gather(*(get_username_by_id(cid, callback.bot) for cid in creator_ids)),
        asyncio.gather(*(get_topic_name_by_thread_id(event.get("thread_id")) for event in events)),
    )
    usernames = {
        cid: (name or str(cid))
        for cid, name in zip(creator_ids, resolved_names)
    }
    for event, topic_name in zip(events, topic_names):
        event["topic_name"] = topic_name or "Основной чат"
        event["event_link"] = build_event_message_link(
            GROUP_ID, event.get("message_id"), event.get("thread_id")
        )

    text = format_digest_text(events, usernames, period=period)
    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    await finalize_callback(
        callback,
        delete_message=CALLBACK_DELETE_WIZARD_MESSAGE,
        skip_answer=True,
    )
