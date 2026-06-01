"""Клавиатуры (inline/reply) для пользовательских сценариев бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import category_badge


def cancel_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура отмены с опциональным шагом назад."""
    rows: list[list[InlineKeyboardButton]] = []
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_actions(event_id: int, carpool_enabled: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для мероприятия."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Пойду", callback_data=f"join_{event_id}")
    builder.button(text="❌ Отказаться", callback_data=f"decline_{event_id}")
    builder.button(text="⏳ В резерв", callback_data=f"waitlist_{event_id}")
    if carpool_enabled:
        builder.button(text="🚗 Еду на машине", callback_data=f"driver_{event_id}")
        builder.button(text="👥 Ищу попутку", callback_data=f"passenger_{event_id}")
    builder.button(text="🗑 Удалить мероприятие", callback_data=f"delete_{event_id}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def choose_topic_keyboard(topics: list[dict], back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора темы с реальными названиями."""
    builder = InlineKeyboardBuilder()

    builder.button(text="📌 В основной чат", callback_data="topic_0")

    for topic in topics:
        topic_id = topic.get("message_thread_id") or topic.get("id")
        topic_name = topic.get("name", f"Тема {topic_id}")
        builder.button(text=f"📁 {topic_name}", callback_data=f"topic_{topic_id}")

    if back_callback:
        builder.button(text="↩️ Назад", callback_data=back_callback)
    builder.button(text="❌ Отмена", callback_data="cancel_create")
    builder.adjust(1)
    return builder.as_markup()


def skip_field_keyboard(field: str, back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Кнопка для пропуска опционального шага с опциональным шагом назад."""
    rows = [[InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{field}")]]
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def event_period_mode_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки выбора: разовое мероприятие или период действия."""
    rows = [
        [InlineKeyboardButton(text="📍 Разовое мероприятие", callback_data="event_period_none")],
        [InlineKeyboardButton(text="📚 Период действия", callback_data="event_period_range")],
    ]
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_preview_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения мини-превью мероприятия."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Опубликовать", callback_data="event_preview_publish")],
            [InlineKeyboardButton(text="↩️ К категориям", callback_data="event_back")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")],
        ]
    )


def quick_event_templates_keyboard() -> InlineKeyboardMarkup:
    """Быстрые сценарии создания мероприятий."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💪 Спорт", callback_data="template_event_sport"),
                InlineKeyboardButton(text="🗣 Языковой клуб", callback_data="template_event_language"),
            ],
            [
                InlineKeyboardButton(text="🍔 Еда", callback_data="template_event_food"),
                InlineKeyboardButton(text="🎬 Кино", callback_data="template_event_movie"),
            ],
            [
                InlineKeyboardButton(text="🔭 Астрономия", callback_data="template_event_astronomy"),
                InlineKeyboardButton(text="🎓 Лекция", callback_data="template_event_lecture"),
            ],
            [
                InlineKeyboardButton(text="🏎 Картинг", callback_data="template_event_karting"),
                InlineKeyboardButton(text="🖥 Кооп на ПК", callback_data="template_event_pc_coop"),
            ],            
            [
                InlineKeyboardButton(text="📚 Книжный клуб", callback_data="template_event_book"),
                InlineKeyboardButton(text="🧠 Квиз", callback_data="template_event_quiz"),
            ],
            [
                InlineKeyboardButton(text="🎲 Настолки", callback_data="template_event_boardgames"),
                InlineKeyboardButton(text="🚶 Прогулка", callback_data="template_event_walk"),
            ],
            [InlineKeyboardButton(text="🏠 В события", callback_data="menu_events")],
        ]
    )


def start_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка перехода из /start в главное меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Открыть /menu", callback_data="menu_home")]]
    )


def main_menu_keyboard(is_admin_or_owner: bool = False) -> InlineKeyboardMarkup:
    """Визуальное меню основных команд для личных сообщений."""
    rows = [
        [InlineKeyboardButton(text="🎉 События", callback_data="menu_events")],
        [InlineKeyboardButton(text="🧾 Деньги", callback_data="menu_money")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu_notifications")],
        [InlineKeyboardButton(text="🤝 Комьюнити", callback_data="menu_community")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")],
    ]
    if is_admin_or_owner:
        rows.append([InlineKeyboardButton(text="Админ", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def menu_section_keyboard(section: str, is_admin_or_owner: bool = False) -> InlineKeyboardMarkup:
    """Кнопки команд внутри выбранного раздела меню."""
    section_rows: dict[str, list[list[InlineKeyboardButton]]] = {
        "events": [
            [InlineKeyboardButton(text="🎉 /create_event", callback_data="menu_action_create_event")],
            [InlineKeyboardButton(text="⚡ Быстрые шаблоны", callback_data="menu_quick")],
            [InlineKeyboardButton(text="📅 /my_events", callback_data="menu_action_my_events")],
            [InlineKeyboardButton(text="📣 /digest", callback_data="menu_action_digest")],
            [InlineKeyboardButton(text="🔎 /find_events", callback_data="menu_cmd_find_events")],
            [InlineKeyboardButton(text="🔗 /send_event_card", callback_data="menu_cmd_send_event_card")],
            [InlineKeyboardButton(text="👤 /set_responsible", callback_data="menu_cmd_set_responsible")],
            [InlineKeyboardButton(text="➕ /add_participant_manual", callback_data="menu_cmd_add_participant_manual")],
            [InlineKeyboardButton(text="🚗 /set_carpool_manual", callback_data="menu_cmd_set_carpool_manual")],
            [InlineKeyboardButton(text="👥 /add_passenger_manual", callback_data="menu_cmd_add_passenger_manual")],
        ],
        "notifications": [
            [InlineKeyboardButton(text="🔔 /subscriptions", callback_data="menu_action_subscriptions")],
            [InlineKeyboardButton(text="✨ /my_digest", callback_data="menu_action_my_digest")],
        ],
        "community": [
            [
                InlineKeyboardButton(text="🤝 /random_optin", callback_data="menu_action_random_optin"),
                InlineKeyboardButton(text="🚫 /random_optout", callback_data="menu_action_random_optout"),
            ],
            [
                InlineKeyboardButton(text="📈 /my_stats", callback_data="menu_action_my_stats"),
                InlineKeyboardButton(text="🏆 /top", callback_data="menu_action_top"),
            ],
        ],
        "help": [
            [InlineKeyboardButton(text="❓ /help", callback_data="menu_cmd_help")],
            [InlineKeyboardButton(text="✅ /status", callback_data="menu_cmd_status")],
        ],
        "money": [
            [InlineKeyboardButton(text="🧾 /split_bill", callback_data="menu_action_split_bill")],
            [
                InlineKeyboardButton(text="➕ /split_bill_add", callback_data="menu_cmd_split_bill_add"),
                InlineKeyboardButton(text="➖ /split_bill_remove", callback_data="menu_cmd_split_bill_remove"),
            ],
        ],
    }
    if is_admin_or_owner:
        section_rows["admin"] = [
            [
                InlineKeyboardButton(text="Роли", callback_data="menu_action_roles"),
                InlineKeyboardButton(text="Статы", callback_data="menu_action_usage_stats"),
            ],
            [InlineKeyboardButton(text="Отчёт", callback_data="menu_action_admin_report")],
            [InlineKeyboardButton(text="Афиша", callback_data="menu_action_send_events_list")],
            [InlineKeyboardButton(text="Возврат", callback_data="menu_cmd_member_reengage")],
            [InlineKeyboardButton(text="Синхр.", callback_data="menu_cmd_sync_members")],
            [InlineKeyboardButton(text="Интро", callback_data="menu_cmd_pending_intro")],
            [
                InlineKeyboardButton(text="Диагн.", callback_data="menu_cmd_debug_info"),
                InlineKeyboardButton(text="Темы", callback_data="menu_cmd_list_topics"),
            ],
            [InlineKeyboardButton(text="Имена тем", callback_data="menu_cmd_update_topic_names")],
            [InlineKeyboardButton(text="Пары", callback_data="menu_action_random_pairs")],
            [InlineKeyboardButton(text="1:1", callback_data="menu_cmd_random_optin_count")],
        ]

    rows = section_rows.get(section, []) + [[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu_home")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_price_mode_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки выбора модели стоимости мероприятия."""
    rows = [
        [InlineKeyboardButton(text="💰 Общая сумма", callback_data="price_mode_total")],
        [InlineKeyboardButton(text="👤 С человека", callback_data="price_mode_person")],
        [InlineKeyboardButton(text="🆓 Бесплатно", callback_data="price_mode_free")],
    ]
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def carpool_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки выбора карпулинга."""
    rows = [
        [
            InlineKeyboardButton(text="✅ Да", callback_data="carpool_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="carpool_no"),
        ],
    ]
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_groups_keyboard(category_groups: dict[str, dict], back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура с группами категорий."""
    builder = InlineKeyboardBuilder()
    for group_key, group_data in category_groups.items():
        builder.button(
            text=str(group_data["title"]),
            callback_data=f"category_group_{group_key}",
        )
    builder.button(text="✅ Готово", callback_data="category_done")
    if back_callback:
        builder.button(text="↩️ Назад", callback_data=back_callback)    
    builder.button(text="❌ Отмена", callback_data="cancel_create")
    builder.adjust(1)
    return builder.as_markup()


def category_subgroups_keyboard(
    group_key: str,
    category_groups: dict[str, dict],
    selected_categories: list[str],
) -> InlineKeyboardMarkup:
    """Клавиатура выбора подкатегорий (множественный выбор)."""
    builder = InlineKeyboardBuilder()
    group = category_groups[group_key]
    subcategories = group["subcategories"]

    for category in subcategories:
        marker = "✅ " if category in selected_categories else ""
        builder.button(
            text=f"{marker}{category_badge(category)}",
            callback_data=f"category_toggle_{category}",
        )

    builder.button(text="↩️ К группам", callback_data="category_back")
    builder.button(text="✅ Готово", callback_data="category_done")
    builder.button(text="❌ Отмена", callback_data="cancel_create")
    builder.adjust(1, 1, 1, 1, 1, 1)
    return builder.as_markup()


def my_events_keyboard(events: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком мероприятий пользователя."""
    builder = InlineKeyboardBuilder()
    for event in events[:10]:  # Максимум 10
        builder.button(
            text=f"📅 {event['title'][:20]}", callback_data=f"myevent_{event['id']}"
        )
    builder.adjust(1)
    return builder.as_markup()


def period_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Универсальная клавиатура выбора периода."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📆 За неделю", callback_data=f"{prefix}_week")
    builder.button(text="🗓 За месяц", callback_data=f"{prefix}_month")
    builder.button(text="🧾 За всё время", callback_data=f"{prefix}_all")
    builder.adjust(1)
    return builder.as_markup()


def broadcast_topics_keyboard(topics: list[dict], period: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора подгруппы для публикации списка мероприятий."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 В основной чат", callback_data=f"broadcast_topic_{period}_0")

    for topic in topics:
        topic_id = topic.get("message_thread_id") or topic.get("id")
        topic_name = topic.get("name", f"Тема {topic_id}")
        builder.button(
            text=f"📁 {topic_name}",
            callback_data=f"broadcast_topic_{period}_{topic_id}",
        )

    builder.adjust(1)
    return builder.as_markup()


def random_pairs_topics_keyboard(topics: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура выбора подгруппы для публикации random 1:1 пар."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 В основной чат", callback_data="random_pairs_topic_0")

    for topic in topics:
        topic_id = topic.get("message_thread_id") or topic.get("id")
        topic_name = topic.get("name", f"Тема {topic_id}")
        builder.button(
            text=f"📁 {topic_name}",
            callback_data=f"random_pairs_topic_{topic_id}",
        )

    builder.adjust(1)
    return builder.as_markup()


def notification_settings_keyboard(current: str) -> InlineKeyboardMarkup:
    """Клавиатура настроек уведомлений."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 Все уведомления", callback_data="notify_all")
    builder.button(text="📍 Только мои", callback_data="notify_mine")
    builder.button(text="🔕 Отключить", callback_data="notify_off")
    if current == "all":
        builder.button(text="✅ Текущее: Все", callback_data="notify_current")
    elif current == "mine":
        builder.button(text="✅ Текущее: Только мои", callback_data="notify_current")
    else:
        builder.button(text="✅ Текущее: Отключено", callback_data="notify_current")
    builder.adjust(1)
    return builder.as_markup()


def onboarding_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Старт", callback_data="onboarding_start")]
        ]
    )


def rules_ack_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Правила изучил(а) ❤️", callback_data="rules_ack")]
        ]
    )


def owner_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять в группу", callback_data=f"approve_user_{user_id}"),
                InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_user_{user_id}"),
            ]
        ]
    )


def intro_status_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"intro_done_{user_id}"),
                InlineKeyboardButton(text="✏️ Изменить статус", callback_data=f"intro_toggle_{user_id}"),
            ]
        ]
    )