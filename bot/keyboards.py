"""Клавиатуры (inline/reply) для пользовательских сценариев бота."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import DONATION_SBERBANK_URL, DONATION_TBANK_URL
from bot.constants import category_badge


def cancel_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура отмены с опциональным шагом назад."""
    rows: list[list[InlineKeyboardButton]] = []
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_actions(event_id: int, carpool_enabled: bool = False) -> InlineKeyboardMarkup:
    """Компактные CTA-кнопки карточки мероприятия."""
    rows = [
        [
            InlineKeyboardButton(text="✅ В путь!", callback_data=f"join_{event_id}"),
            InlineKeyboardButton(text="⏳ В резерве", callback_data=f"waitlist_{event_id}"),
        ],
        [InlineKeyboardButton(text="❌ В другой раз", callback_data=f"decline_{event_id}")],
    ]
    if carpool_enabled:
        rows.append(
            [
                InlineKeyboardButton(text="🚗 Водитель", callback_data=f"driver_{event_id}"),
                InlineKeyboardButton(text="👥 Попутка", callback_data=f"passenger_{event_id}"),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="🙋 Ищу попутку", callback_data=f"seek_ride_{event_id}")]
        )
    rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def attendance_confirmation_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Всё ещё иду",
                    callback_data=f"confirm_attendance_{event_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Не смогу",
                    callback_data=f"decline_attendance_{event_id}",
                )
            ],
        ]
    )


def choose_topic_keyboard(topics: list[dict], back_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора темы с реальными названиями."""
    builder = InlineKeyboardBuilder()

    builder.button(text="📌 В основной чат", callback_data="topic_0")

    for topic in topics:
        topic_id = topic.get("message_thread_id") or topic.get("id")
        topic_name = topic.get("name", f"Тема {topic_id}")
        builder.button(text=f"{topic_name}", callback_data=f"topic_{topic_id}")

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
            [InlineKeyboardButton(text="🗺️ Публикуем!", callback_data="event_preview_publish")],
            [InlineKeyboardButton(text="↩️ К категориям", callback_data="event_back")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")],
        ]
    )


def template_field_keyboard(
    keep_callback: str,
    custom_callback: str,
    *,
    skip_callback: str | None = None,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """Выбор: оставить значение шаблона или ввести своё."""
    rows = [
        [InlineKeyboardButton(text="✅ Оставить из шаблона", callback_data=keep_callback)],
        [InlineKeyboardButton(text="✏️ Ввести своё", callback_data=custom_callback)],
    ]
    if skip_callback:
        rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_callback)])
    if back_callback:
        rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_event_fields_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Меню выбора поля для редактирования мероприятия."""
    prefix = f"edit_field_{event_id}_"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Название", callback_data=f"{prefix}title")],
            [InlineKeyboardButton(text="📄 Описание", callback_data=f"{prefix}description")],
            [InlineKeyboardButton(text="🗓 Дата и время", callback_data=f"{prefix}datetime")],
            [InlineKeyboardButton(text="📆 Конец периода", callback_data=f"{prefix}period_end")],
            [InlineKeyboardButton(text="⏱ Длительность", callback_data=f"{prefix}duration")],
            [InlineKeyboardButton(text="📍 Место", callback_data=f"{prefix}location")],
            [InlineKeyboardButton(text="💰 Стоимость", callback_data=f"{prefix}price")],
            [InlineKeyboardButton(text="👥 Лимит участников", callback_data=f"{prefix}limit")],
            [InlineKeyboardButton(text="🚗 Карпулинг", callback_data=f"{prefix}carpool")],
            [InlineKeyboardButton(text="📂 Категории", callback_data=f"{prefix}category")],
            [InlineKeyboardButton(text="✅ Готово", callback_data=f"edit_done_{event_id}")],
        ]
    )


def edit_event_price_mode_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Режим стоимости при редактировании."""
    prefix = f"edit_price_{event_id}_"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆓 Бесплатно", callback_data=f"{prefix}free")],
            [InlineKeyboardButton(text="💵 Общая сумма", callback_data=f"{prefix}total")],
            [InlineKeyboardButton(text="👤 С человека", callback_data=f"{prefix}person")],
            [InlineKeyboardButton(text="↩️ К полям", callback_data=f"edit_menu_{event_id}")],
        ]
    )


def edit_event_carpool_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"edit_carpool_{event_id}_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"edit_carpool_{event_id}_no"),
            ],
            [InlineKeyboardButton(text="↩️ К полям", callback_data=f"edit_menu_{event_id}")],
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


def donation_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопки-ссылки на сборы Сбербанка и Т-Банка."""
    rows: list[list[InlineKeyboardButton]] = []
    if DONATION_SBERBANK_URL:
        rows.append([InlineKeyboardButton(text="💚 Сбор в Сбербанке", url=DONATION_SBERBANK_URL)])
    if DONATION_TBANK_URL:
        rows.append([InlineKeyboardButton(text="💛 Сбор в Т-Банке", url=DONATION_TBANK_URL)])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="✏️ /edit_event", callback_data="menu_cmd_edit_event")],
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
            [InlineKeyboardButton(text="☕ /donate", callback_data="menu_action_donate")],
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
                InlineKeyboardButton(text="🛡 /roles", callback_data="menu_action_roles"),
                InlineKeyboardButton(text="📊 /usage_stats", callback_data="menu_action_usage_stats"),
            ],
            [InlineKeyboardButton(text="📋 /admin_report", callback_data="menu_action_admin_report")],
            [InlineKeyboardButton(text="📣 /send_events_list", callback_data="menu_action_send_events_list")],
            [InlineKeyboardButton(text="💬 /member_reengage", callback_data="menu_cmd_member_reengage")],
            [InlineKeyboardButton(text="🔄 /sync_members", callback_data="menu_cmd_sync_members")],
            [InlineKeyboardButton(text="📝 /pending_intro", callback_data="menu_cmd_pending_intro")],
            [
                InlineKeyboardButton(text="🔧 /debug_info", callback_data="menu_cmd_debug_info"),
                InlineKeyboardButton(text="🗂 /list_topics", callback_data="menu_cmd_list_topics"),
            ],
            [InlineKeyboardButton(text="🏷 /update_topic_names", callback_data="menu_cmd_update_topic_names")],
            [InlineKeyboardButton(text="🤝 /random_pairs", callback_data="menu_action_random_pairs")],
            [InlineKeyboardButton(text="👥 /random_optin_count", callback_data="menu_cmd_random_optin_count")],
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
            text=f"{marker}{category_badge(category)} · {category}",
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
            text=topic_name,
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
            text=topic_name,
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