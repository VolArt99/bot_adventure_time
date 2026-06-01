from __future__ import annotations

from bot.utils.design import BRAND, card_cta, card_header, card_section


MENU_BUTTON_DESCRIPTIONS = {
    "🎉 Создать": "запустить мастер события: дата, место, цена, лимит, тема публикации.",
    "📅 Мои": "открыть период и список ваших мероприятий для управления.",
    "🧾 Чек": "создать split-bill карточку и собрать статусы оплат.",
    "📣 Афиша": "посмотреть общий дайджест и найти ближайшие события.",
    "🔔 Подписки": "выбрать интересы для персональных уведомлений и дайджеста.",
    "🤝 Комьюнити": "включить random 1:1, посмотреть статистику и топ участников.",
    "⚡ Быстрые сценарии": "создать событие из готового шаблона за несколько кликов.",
    "🧭 Все команды": "перейти к сгруппированному каталогу команд и примеров.",
    "❓ Помощь": "открыть подробную справку по ролям, сценариям и кнопкам.",
    "Админ": "отчёты, диагностика, публикации и служебные действия для админов.",
}

SECTION_BUTTON_DESCRIPTIONS = {
    "create_event": [
        "🎉 /create_event — пошаговый мастер новой карточки события.",
        "⚡ Быстрые шаблоны — подставить типовые название, описание и категорию.",
    ],
    "my_events": [
        "📅 /my_events — список ваших событий за выбранный период.",
        "🔗 /send_event_card — короткая ссылка на основную карточку без дублирования интерактива.",
        "👤 /set_responsible — сменить ответственного за событие.",
        "➕ /add_participant_manual — добавить участника вручную.",
        "🚗 /set_carpool_manual — назначить или сбросить водителя и места.",
        "👥 /add_passenger_manual — привязать пассажира к водителю.",
    ],
    "split_bill": [
        "🧾 /split_bill — мастер чека с публикацией карточки сбора.",
        "➕ /split_bill_add — добавить участника вручную.",
        "➖ /split_bill_remove — удалить участника из чека.",
    ],
    "digest": [
        "📣 /digest — общая афиша за выбранный период.",
        "✨ /my_digest — персональная подборка по подпискам.",
        "🔎 /find_events — поиск события по названию, описанию или месту.",
    ],
    "subscriptions": [
        "🔔 /subscriptions — выбрать категории интересов.",
        "✨ /my_digest — сразу получить персональную подборку.",
    ],
    "community": [
        "🤝 /random_optin — участвовать в random 1:1.",
        "🚫 /random_optout — выйти из random 1:1.",
        "📈 /my_stats — личная статистика участий.",
        "🏆 /top — топ активности за 30 дней.",
    ],
    "help": [
        "❓ /help — подробная справка.",
        "✅ /status — быстрый health-check бота.",
    ],
    "commands": [
        "🚀 База — старт, меню, помощь и статус.",
        "🎉 События — создание и управление мероприятиями.",
        "📣 Афиша — дайджесты и поиск.",
        "🔔 Подписки — интересы и персональный дайджест.",
        "🤝 Комьюнити — 1:1 и активность.",
        "🧾 Чеки — split-bill сценарии.",
    ],
    "quick": [
        "📚 Книжный клуб — встреча для обсуждения книги.",
        "🧠 Квиз — интеллектуальная игра.",
        "🎲 Настолки — настольные игры.",
        "🚶 Прогулка — прогулка или офлайн-маршрут.",
        "🍽 Ужин — совместный ужин.",
        "🏠 В меню — вернуться к созданию мероприятия.",
    ],
}

ADMIN_BUTTON_DESCRIPTIONS = [
    "Роли — модель доступа и лимиты.",
    "Статы — среднее использование команд за 7 дней.",
    "Отчёт — активность, явка и топ категорий.",
    "Афиша — публикация списка мероприятий.",
    "Возврат — подсказки по молчащим участникам.",
    "Синхр. — очистка локального списка участников.",
    "Интро — контроль рассказов о себе.",
    "Диагн. / Темы / Имена тем — диагностика и синхронизация форум-тем.",
    "Пары / 1:1 — публикация random-пар и число согласных.",
]

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
                f"{BRAND['event']} <b>События</b> — создать встречу, афишу, быстрый шаблон.",
                f"{BRAND['money']} <b>Деньги</b> — разделить чек и отметить оплаты.",
                f"{BRAND['notify']} <b>Уведомления</b> — подписки и персональные дайджесты.",
                f"{BRAND['community']} <b>Комьюнити</b> — random 1:1 и активность.",
            ],
        ),
        *card_section("Что делает каждая кнопка", _button_description_lines(MENU_BUTTON_DESCRIPTIONS)),
        *card_cta("Выберите действие кнопкой ниже."),
    ]
    if is_admin_or_owner:
        lines.insert(-2, f"{BRAND['admin']} <i>Вам доступен админ-раздел.</i>")
    return "\n".join(lines)


def build_menu_section_text(section: str, *, is_admin_or_owner: bool) -> str | None:
    """Возвращает красивую карточку раздела главного меню."""
    sections = {
        "create_event": (
            [
                *card_header(BRAND["event"], "Создание мероприятия", "Мастер карточки события"),
                *card_section(
                    "Что заполнит мастер",
                    [
                        "• название, описание, дату старта и период действия;",
                        "• место, стоимость, лимит, карпулинг и тему публикации;",
                        "• перед публикацией покажет мини-превью карточки.",
                    ],
                ),
                *card_cta("Команда: /create_event или быстрый шаблон ниже."),
            ]
        ),
        "my_events": (
            [
                *card_header(BRAND["calendar"], "Мои мероприятия", "Управление созданными событиями"),
                *card_section("Возможности", ["• посмотреть свои события;", "• отправить ссылку на карточку;", "• назначить ответственного или добавить участника."]),
                *card_cta("Команда: /my_events"),
            ]
        ),
        "split_bill": (
            [
                *card_header(BRAND["money"], "Разделение чека", "Карточка сбора и статусы оплат"),
                *card_section("Что будет в карточке", ["• сумма и доля на участника;", "• реквизиты и получатель;", "• визуальная шкала: ✅ оплатили / ⏳ ждём."]),
                *card_cta("Команда: /split_bill"),
            ]
        ),
        "digest": (
            [
                *card_header("📣", "Афиша и поиск", "Быстрый доступ к событиям"),
                *card_section("Команды", ["• /digest — общая афиша;", "• /my_digest — персональная подборка;", "• <code>/find_events &lt;текст&gt;</code> — поиск."]),
                *card_cta("Выберите афишу или используйте поиск."),
            ]
        ),
        "subscriptions": (
            [
                *card_header(BRAND["notify"], "Подписки и уведомления", "Только релевантные события"),
                *card_section("Настройки", ["• категории интересов;", "• персональный дайджест;", "• режим уведомлений."]),
                *card_cta("Команды: /subscriptions, /my_digest"),
            ]
        ),
        "community": (
            [
                *card_header(BRAND["community"], "Комьюнити и активность", "Знакомства и статистика"),
                *card_section("Команды", ["• /random_optin и /random_optout — random 1:1;", "• /my_stats — личная статистика;", "• /top — топ активности."]),
                *card_cta("Включайтесь в комьюнити-активности."),
            ]
        ),
        "help": (
            [
                *card_header(BRAND["help"], "Помощь", "Справка по командам"),
                *card_section("Быстрые кнопки", ["• /help — полная справка по ролям и сценариям;", "• /status — проверить, что бот онлайн;", "• /menu — вернуться в Control Center."]),
                *card_cta("Выберите команду кнопкой ниже."),
            ]
        ),
        "commands": (
            [
                *card_header("🧭", "Все команды", "Разделы и подгруппы вместо ручного ввода"),
                *card_section("Как пользоваться", ["• откройте нужную группу кнопкой ниже;", "• команды с параметрами покажут пример заполнения;", "• основные сценарии запускаются из своих разделов меню."]),
                *card_cta("Выберите группу команд."),
            ]
        ),
        "quick": (
            [
                *card_header(BRAND["event"], "Быстрые сценарии", "Шаблоны для мастера мероприятия"),
                *card_section("Доступные шаблоны", ["📚 Книжный клуб", "🧠 Квиз", "🎲 Настолки", "🚶 Прогулка", "🍽 Ужин" ]),
                *card_cta("Нажмите шаблон — бот подставит название, описание и категорию."),
            ]
        ),
    }
    if section == "admin":
        if not is_admin_or_owner:
            return None
        return "\n".join([
            *card_header("Админ", "Панель", "Отчёты, публикации, диагностика"),
            *card_section("Действия", ["• Отчёт / Статы — метрики;", "• Афиша — список мероприятий;", "• Интро — контроль рассказа о себе;", "• Темы / Диагн. — диагностика."]),
            *card_section("Кнопки раздела", _button_description_lines(ADMIN_BUTTON_DESCRIPTIONS)),
            *card_cta("Выберите короткую action-кнопку ниже."),
        ])
    section_lines = sections.get(section)
    if not section_lines:
        return None
    button_descriptions = SECTION_BUTTON_DESCRIPTIONS.get(section)
    if button_descriptions:
        section_lines = [
            *section_lines[:-1],
            *card_section("Кнопки раздела", _button_description_lines(button_descriptions)),
            section_lines[-1],
        ]
    return "\n".join(section_lines)


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
