from __future__ import annotations

from bot.utils.design import BRAND, card_cta, card_header, card_section


MENU_BUTTON_DESCRIPTIONS = {
    "🎉 События": "создать встречу, открыть афишу, найти событие или управлять своей карточкой.",
    "🧾 Деньги": "собрать split-bill, участников и статусы оплат в одном месте.",
    "🔔 Уведомления": "настроить интересы и получать персональную подборку.",
    "🤝 Комьюнити": "включить random 1:1 и посмотреть активность участников.",
    "❓ Помощь": "прочитать справку без лишней клавиатуры внизу.",
    "Админ": "отчёты, диагностика и служебные действия для админов.",
}

SECTION_TONES = {
    "events": {
        "icon": "🟣🎉",
        "title": "События",
        "subtitle": "Афиша, создание и управление встречами",
        "focus": [
            "• быстрый путь к созданию и шаблонам;",
            "• афиша, поиск и ваши мероприятия;",
            "• служебные действия только по карточкам событий.",
        ],
        "cta": "Выберите действие по событиям ниже.",
    },
    "money": {
        "icon": "🟢🧾",
        "title": "Деньги",
        "subtitle": "Чеки и статусы оплат",
        "focus": [
            "• создать split-bill карточку;",
            "• вручную добавить или удалить участника;",
            "• быстро вернуться к оплатам без поиска команд.",
        ],
        "cta": "Выберите действие по деньгам ниже.",
    },
    "notifications": {
        "icon": "🔵🔔",
        "title": "Уведомления",
        "subtitle": "Интересы и персональные дайджесты",
        "focus": [
            "• выбрать категории интересов;",
            "• получить персональную подборку;",
            "• держать ленту событий релевантной.",
        ],
        "cta": "Настройте подписки или откройте персональный дайджест.",
    },
    "community": {
        "icon": "🟠🤝",
        "title": "Комьюнити",
        "subtitle": "Знакомства и активность",
        "focus": [
            "• включить или выключить random 1:1;",
            "• посмотреть личную статистику;",
            "• открыть топ активности за 30 дней.",
        ],
        "cta": "Выберите комьюнити-действие ниже.",
    },
    "help": {
        "icon": "⚪❓",
        "title": "Помощь",
        "subtitle": "Справка и быстрый статус",
        "focus": [
            "• /help отправит чистую справку без меню;",
            "• /status быстро проверит, что бот онлайн.",
        ],
        "cta": "Откройте справку или проверьте статус.",
    },
    "quick": {
        "icon": "🟣⚡",
        "title": "Быстрые сценарии",
        "subtitle": "Шаблоны для мастера мероприятия",
        "focus": [
            "• спорт, язык, еда, кино и лекции;",
            "• астрономия, картинг и кооперативная игра на ПК;",
            "• также доступны книжный клуб, квиз, настолки и прогулка.",
        ],
        "cta": "Нажмите шаблон — бот подставит название, описание и категорию.",
    },
}

INLINE_BUTTON_HELP = [
    "✅ Пойду / ❌ Отказаться / ⏳ В резерв — обновляют статус участия в карточке мероприятия.",
    "🚗 Еду на машине / 👥 Ищу попутку — включают карпулинг для события, если он разрешён.",
    "🗑 Удалить мероприятие — удаляет событие у создателя/админа после проверки прав.",
    "↩️ Назад / ❌ Отмена / ⏭ Пропустить — навигация в мастерах без ручного ввода команд.",
    "🚀 Опубликовать — финальная публикация события после превью.",
    "📌 В основной чат / 📁 Тема — выбор места публикации в группе или forum topic.",
    "📆 За неделю / 🗓 За месяц / 🧾 За всё время — выбор периода для списков и дайджестов.",
    "✅ Присоединиться / 🚪 Выйти / 💸 Оплатил(а) / 🔄 Обновить / 🔒 Закрыть чек — управление split-bill карточкой.",
    "✅ Подписаться на всё / 🚫 Отписаться от всего / 💾 Сохранить — массовые действия в подписках.",
]


def _button_description_lines(items) -> list[str]:
    if isinstance(items, dict):
        return [f"• <b>{label}</b> — {description}" for label, description in items.items()]
    return [f"• {item}" for item in items]


def build_main_menu_text(*, is_admin_or_owner: bool) -> str:
    """Стильный текст главного меню в ЛС."""
    lines = [
        *card_header("✨", "Adventure Time Control Center", "Единая панель действий бота"),
        *card_section(
            "Разделы",
            [
                "🟣🎉 <b>События</b> — создать встречу, афишу, быстрый шаблон.",
                "🟢🧾 <b>Деньги</b> — разделить чек и отметить оплаты.",
                "🔵🔔 <b>Уведомления</b> — подписки и персональные дайджесты.",
                "🟠🤝 <b>Комьюнити</b> — random 1:1 и активность.",
            ],
        ),
        *card_section("Что делает каждая кнопка", _button_description_lines(MENU_BUTTON_DESCRIPTIONS)),
        *card_cta("Выберите действие кнопкой ниже."),
    ]
    if is_admin_or_owner:
        lines.insert(-2, f"{BRAND['admin']} <i>Вам доступен админ-раздел.</i>")
    return "\n".join(lines)


def build_menu_section_text(section: str, *, is_admin_or_owner: bool) -> str | None:
    """Возвращает короткую карточку раздела главного меню."""
    if section == "admin":
        if not is_admin_or_owner:
            return None
        return "\n".join([
            *card_header("🔴🛡", "Админ", "Отчёты, публикации, диагностика"),
            *card_section("Фокус", ["• метрики и отчёты;", "• темы, интро и синхронизация;", "• публикации и random 1:1."]),
            *card_cta("Выберите админ-действие ниже."),
        ])
    
    tone = SECTION_TONES.get(section)
    if not tone:
        return None
    
    return "\n".join([
        *card_header(str(tone["icon"]), str(tone["title"]), str(tone["subtitle"])),
        *card_section("Фокус", list(tone["focus"])),
        *card_cta(str(tone["cta"])),
    ])


from bot.commands import COMMANDS_BY_KEY


COMMAND_ACTIONS = {
    key: (spec.display_syntax, spec.description)
    for key, spec in COMMANDS_BY_KEY.items()
}

# Legacy overrides with rich examples.
COMMAND_ACTIONS.update({
    "help": ("/help", "Подробная справка по ролям и сценариям."),
    "menu": ("/menu", "Главное кнопочное меню."),
    "status": ("/status", "Проверить, что бот онлайн."),
    "create_event": ("/create_event", "Запустить мастер создания мероприятия."),
    "my_events": ("/my_events", "Открыть список ваших мероприятий."),
    "find_events": ("/find_events &lt;текст&gt;", "Поиск активных мероприятий. Пример: <code>/find_events квиз</code>"),
    "set_responsible": ("/set_responsible &lt;event_id&gt; &lt;user_id|@username&gt;", "Сменить ответственного. Пример: <code>/set_responsible 42 @ivan</code>"),
    "add_participant_manual": ("/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;", "Добавить участника вручную. Пример: <code>/add_participant_manual 42 @ivan</code>"),
    "set_carpool_manual": ("/set_carpool_manual &lt;event_id&gt; &lt;driver_id|@driver&gt; &lt;seats&gt;", "Ручное управление статусом карпулинга."),
    "add_passenger_manual": ("/add_passenger_manual &lt;event_id&gt; &lt;passenger_id|@passenger&gt; &lt;driver_id|@driver&gt;", "Ручное добавление пассажира к водителю."),
    "send_event_card": ("/send_event_card &lt;event_id&gt;", "Отправить короткое сообщение со ссылкой на основную карточку мероприятия."),
    "digest": ("/digest", "Открыть общую афишу."),
    "subscriptions": ("/subscriptions", "Настроить подписки и уведомления."),
    "my_digest": ("/my_digest", "Получить персональный дайджест."),
    "my_stats": ("/my_stats", "Посмотреть личную статистику участий."),
    "top": ("/top", "Показать топ активности за 30 дней."),
    "random_optin": ("/random_optin", "Включиться в random-встречи 1:1."),
    "random_optout": ("/random_optout", "Выключиться из random-встреч 1:1."),
    "split_bill": ("/split_bill", "Запустить мастер разделения чека."),
    "split_bill_add": ("/split_bill_add &lt;id&gt; &lt;user_id|@username&gt;", "Добавить участника в чек вручную."),
    "split_bill_remove": ("/split_bill_remove &lt;id&gt; &lt;user_id&gt;", "Удалить участника из чека вручную."),
    "roles": ("/roles", "Показать роли и лимиты."),
    "usage_stats": ("/usage_stats", "Статистика использования команд."),
    "debug_info": ("/debug_info", "Диагностическая сводка."),
    "list_topics": ("/list_topics", "Показать темы форума из БД."),
    "update_topic_names": ("/update_topic_names", "Синхронизировать названия тем."),
    "admin_report": ("/admin_report", "Управленческий отчёт по активности."),
    "send_events_list": ("/send_events_list", "Опубликовать список мероприятий."),
    "member_reengage": ("/member_reengage", "Отчёт по молчащим участникам."),
    "sync_members": ("/sync_members", "Синхронизировать локальный список участников."),
    "random_pairs": ("/random_pairs", "Сформировать и опубликовать пары 1:1."),
    "pending_intro": ("/pending_intro", "Проверить статус рассказов о себе."),
    "random_optin_count": ("/random_optin_count", "Количество участников, согласных на 1:1."),
})


def build_command_action_text(command_key: str) -> str | None:
    """Карточка-подсказка для кнопки команды."""
    command = COMMAND_ACTIONS.get(command_key)
    if not command:
        return None
    syntax, description = command
    return "\n".join([
        *card_header("⌨️", "Команда", syntax.replace("&lt;", "<").replace("&gt;", ">")),
        *card_section("Что делает", [description]),
        *card_cta("Скопируйте команду или нажмите соответствующий раздел меню."),
    ])


def build_member_help_text() -> str:
    return (
        "ℹ️ <b>Команды участника</b>\n\n"
        "🚀 <b>База</b>\n"
        "• /start — запуск бота и проверка доступа.\n"
        "• /help — показать эту подробную справку.\n"
        "• /menu — открыть стильное кнопочное меню.\n"
        "• /status — быстрый признак, что бот онлайн.\n\n"
        "📅 <b>Мероприятия</b>\n"
        "• /create_event — пошагово создать мероприятие и опубликовать в группе.\n"
        "• /my_events — список ваших мероприятий и управление ими.\n"
        "• <code>/find_events &lt;текст&gt;</code> — поиск активных мероприятий по названию/описанию/месту.\n\n"
        "• <code>/set_responsible &lt;event_id&gt; &lt;user_id|@username&gt;</code> — сменить ответственного (создатель/админ).\n"
        "  Пример: <code>/set_responsible 42 @ivan</code>\n"
        "• <code>/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;</code> — ручное добавление.\n"
        "  Пример: <code>/add_participant_manual 42 @ivan</code>\n"
        "• <code>/send_event_card &lt;event_id&gt;</code> — отправить короткое сообщение со ссылкой на основную карточку мероприятия.\n\n"
        "📰 <b>Дайджест и подписки</b>\n"
        "• /digest — посмотреть афишу на период.\n"
        "• /subscriptions — настроить персональные уведомления.\n"
        "• /my_digest — получить персональный дайджест.\n\n"
        "📈 <b>Активность</b>\n"
        "• /my_stats — ваша статистика участий.\n"
        "• /top — топ активных участников за 30 дней.\n\n"
        "🤝 <b>Случайные встречи 1:1</b>\n"
        "• /random_optin — согласиться участвовать в случайных встречах.\n"
        "• /random_optout — отказаться от случайных встреч.\n\n"
        "💳 <b>Разделение чека</b>\n"
        "• /split_bill — пошагово создать событие разделения чека с публикацией и кнопками.\n"
        "• <code>/split_bill_add &lt;id&gt; &lt;user_id|@username&gt;</code> — добавить участника вручную (организатор).\n\n"
        "🔘 <b>Описание кнопок</b>\n"
        + "\n".join(f"• {line}" for line in INLINE_BUTTON_HELP)
    )


def build_admin_help_text() -> str:
    return (
        "<b>Админ · команды администратора/владельца</b>\n\n"
        "• /roles — текущая модель ролей и лимитов.\n"
        "• /usage_stats — среднее число запросов по ролям за 7 дней.\n"
        "• /debug_info — диагностическая сводка бота/группы/тем.\n"
        "• /list_topics — показать темы форума из БД.\n"
        "• /update_topic_names — синхронизировать названия тем.\n"
        "• /admin_report — управленческий отчёт по активности.\n"
        "• /send_events_list — отправить актуальный список мероприятий в выбранную группу/тему.\n"
        "• /member_reengage — отчёт по «молчащим» участникам и рекомендации, кого мягко позвать.\n"
        "• /sync_members — очистить локальный список участников от выбывших из группы.\n"
        "• /random_pairs — сформировать пары 1:1 и опубликовать их в выбранной группе/теме.\n"
        "• /pending_intro — единый отчёт по «Рассказу о себе» + кнопки отметки статуса.\n"
        "• /random_optin_count — (владелец) количество участников, согласных на 1:1.\n"
    )


def build_help_text(*, is_admin_or_owner: bool) -> str:
    member_help = build_member_help_text()
    if not is_admin_or_owner:
        return member_help
    return build_admin_help_text() + "\n" + member_help
