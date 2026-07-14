from __future__ import annotations

from html import escape

from bot.db.notification_settings import MODE_LABELS
from bot.texts import GROUP_RULES_SHORT_TEXT, get_group_rules_text
from bot.utils.design import (
    BRAND,
    brand_voice,
    card_cta,
    card_header,
    card_section,
    season_copy,
    seasonal_card_divider,
    seasonal_menu_icon,
    seasonal_menu_label,
    step_badge,
)


def build_onboarding_welcome_text() -> str:
    """Приветственный текст первого шага onboarding."""
    return (
        f"{step_badge(1, 3, 'Старт')}\n"
        f"{seasonal_card_divider()}\n"
        f"{brand_voice('onboarding_welcome')}"
    )


def build_approved_member_start_text() -> str:
    """Текст /start для уже подтверждённого участника."""
    return brand_voice("approved_member_start")


def build_group_member_bot_access_denied_text(*, owner_contact_html: str) -> str:
    """Текст для участника группы без одобрения бота."""
    return (
        "👋 Ты уже в группе Telegram, но бот ещё не подтвердил твой доступ.\n\n"
        "Попроси капитана одобрить тебя через бота или дождись ручной синхронизации.\n"
        f"Связаться: {owner_contact_html}"
    )


def build_group_rules_text() -> str:
    """Краткие правила для onboarding-сценария."""
    return (
        f"{step_badge(2, 3, 'Правила')}\n"
        f"{seasonal_card_divider()}\n"
        f"{GROUP_RULES_SHORT_TEXT}\n\n"
        f"<i>ℹ️ Полный текст — по кнопке ниже, если нужны детали.</i>\n\n"
        f"<i>{brand_voice('onboarding_rules_footer')}</i>"
    )


def build_group_rules_full_text() -> str:
    """Полный текст правил группы."""
    return (
        f"{step_badge(2, 3, 'Правила')}\n"
        f"{seasonal_card_divider()}\n"
        f"{get_group_rules_text()}"
    )


def build_rules_accepted_existing_member_text() -> str:
    return brand_voice("rules_accepted_member")


def build_rules_accepted_pending_text() -> str:
    return f"{step_badge(3, 3, 'Заявка')}\n{brand_voice('rules_accepted_pending')}"


def build_pending_request_text() -> str:
    return "⏳ Твоя заявка уже на рассмотрении у капитана ⛵"


def build_onboarding_guard_text() -> str:
    return (
        "Чтобы продолжить, нажми «Старт», затем «Правила изучил(а) ❤️».\n"
        "Любые другие сообщения до этого шага недоступны."
    )


def build_owner_request_text(*, user_id: int, full_name: str, username: str | None) -> str:
    username_text = f"@{username}" if username else "—"
    return (
        "🆕 Запрос на вступление:\n"
        f"• ID: {int(user_id)}\n"
        f"• Имя: {escape(full_name or '—')}\n"
        f"• Username: {escape(username_text)}"
    )


def build_approval_message(*, invite_link: str, owner_contact_html: str) -> str:
    return (
        f"{step_badge(3, 3, 'Вход в группу')}\n"
        f"{seasonal_card_divider()}\n"
        f"{brand_voice('approval_welcome')}\n\n"
        f"{brand_voice('approval_invite')}\n"
        f"{escape(invite_link)}\n\n"
        f"Если возникнут вопросы — напиши капитану: {owner_contact_html}."
    )


def build_rejection_message() -> str:
    return "❌ К сожалению, заявка на вступление отклонена."


def build_owner_only_text() -> str:
    return "❌ Эта команда доступна только владельцу."


def build_not_enough_rights_text() -> str:
    return "🔒 Эта команда доступна только организаторам и администраторам."


SECTION_TONES = {
    "events": {
        "icon": "🎉",
        "title": "События",
        "subtitle": "Афиша, создание и управление встречами",
        "focus": [
            "• <b>Смотреть</b> — афиша, поиск, твои встречи;",
            "• <b>Создать</b> — мастер и быстрые шаблоны;",
            "• <b>Управление</b> — редактирование, участники, карпулинг.",
        ],
        "cta": "Выбери подраздел ниже.",
    },
    "events_browse": {
        "icon": "👀",
        "title": "Смотреть",
        "subtitle": "Афиша и твои встречи",
        "focus": [
            "• общая афиша и персональный дайджест;",
            "• поиск активных мероприятий;",
            "• список твоих встреч.",
        ],
        "cta": "Открой афишу или найди встречу.",
    },
    "events_create": {
        "icon": "➕",
        "title": "Создать",
        "subtitle": "Новая встреча или шаблон",
        "focus": [
            "• мастер создания с нуля;",
            "• шаг «ответственный» при создании карточки;",
            "• быстрые шаблоны: спорт, квиз, прогулка и др.",
        ],
        "cta": "Запусти мастер или выбери шаблон.",
    },
    "events_manage": {
        "icon": "🛠",
        "title": "Управление",
        "subtitle": "Для организаторов и админов",
        "focus": [
            "• редактирование полей карточки;",
            "• назначение ответственного;",
            "• ручное управление участниками и карпулингом.",
        ],
        "cta": "Кнопки с ⌨️ — подсказки по командам. Действия — через «Мои встречи».",
    },
    "money": {
        "icon": "🧾",
        "title": "Скинуться",
        "subtitle": "Собрать деньги с участников",
        "focus": [
            "• создать чек и опубликовать в группе;",
            "• отметить оплаты участников;",
            "• вручную добавить или убрать человека из чека.",
        ],
        "cta": "Соберём команду и разделим расходы.",
    },
    "notifications": {
        "icon": "🔔",
        "title": "Уведомления",
        "subtitle": "Интересы, режим пушей и дайджесты",
        "focus": [
            "• выбрать категории интересов;",
            "• настроить режим уведомлений в ЛС;",
            "• получить персональную подборку.",
        ],
        "cta": "Настрой подписки или режим уведомлений.",
    },
    "notification_mode": {
        "icon": "🔕",
        "title": "Режим уведомлений",
        "subtitle": "Что бот присылает в ЛС",
        "focus": [
            "• <b>Все</b> — подписки и личные напоминания;",
            "• <b>Только мои</b> — явка, резерв, чеки;",
            "• <b>Отключить</b> — без пушей в ЛС.",
        ],
        "cta": "Выбери режим ниже — сохранится сразу.",
    },
    "community": {
        "icon": "🤝",
        "title": "Комьюнити",
        "subtitle": "Знакомства и активность",
        "focus": [
            "• случайные встречи 1:1;",
            "• личная статистика и топ активности;",
            "• день рождения для поздравления в группе.",
        ],
        "cta": "Найди попутчиков и новых друзей.",
    },
    "help": {
        "icon": "❓",
        "title": "Помощь",
        "subtitle": "Справка и быстрый статус",
        "focus": [
            "• /help — подробная справка;",
            "• /status — бот онлайн;",
            "• /donate — поддержать бота.",
        ],
        "cta": "Открой справку или проверь статус.",
    },
    "quick": {
        "icon": "⚡",
        "title": "Быстрые сценарии",
        "subtitle": "Шаблоны для мастера мероприятия",
        "focus": [
            "• спорт, язык, еда, кино и лекции;",
            "• астрономия, картинг и кооперативная игра на ПК;",
            "• также доступны книжный клуб, квиз, настолки и прогулка.",
        ],
        "cta": "Нажми шаблон — затем выбери название, описание или введи свои.",
    },
    "admin": {
        "icon": "🛡",
        "title": "Админ",
        "subtitle": "Отчёты, публикации, диагностика",
        "focus": [
            "• <b>Люди</b> — интро, молчащие, синхронизация;",
            "• <b>Контент</b> — афиша, случайные пары;",
            "• <b>Система</b> — диагностика, темы, лимиты.",
        ],
        "cta": "Выбери группу действий ниже.",
    },
    "admin_people": {
        "icon": "👥",
        "title": "Люди",
        "subtitle": "Участники и интро",
        "focus": [
            "• молчащие участники;",
            "• синхронизация списка;",
            "• рассказы о себе.",
        ],
        "cta": "Кнопки с ⌨️ — подсказки по командам.",
    },
    "admin_content": {
        "icon": "📣",
        "title": "Контент",
        "subtitle": "Публикации в группе",
        "focus": [
            "• отчёт и список мероприятий;",
            "• случайные пары 1:1.",
        ],
        "cta": "Выбери действие ниже.",
    },
    "admin_system": {
        "icon": "⚙️",
        "title": "Система",
        "subtitle": "Диагностика и лимиты",
        "focus": [
            "• роли и статистика команд;",
            "• диагностика и темы форума;",
            "• сброс лимитов участников.",
        ],
        "cta": "Кнопки с ⌨️ — подсказки по командам.",
    },
}

INLINE_BUTTON_HELP = [
    "✅ В путь / ⏳ В резерве / ❌ В другой раз — обновляют статус участия в карточке мероприятия.",
    "В ЛС кнопки показывают твой текущий статус (снять запись, снять резерв).",
    "🛠 Управление (удаление, редактирование) — только в ЛС организатора через «Мои встречи».",
    "🚗 Водитель / 👥 Попутка — включают карпулинг для события, если он разрешён.",
    "🗑 Удалить — только в ЛС организатора, с подтверждением.",
    "↩️ Назад / ❌ Отмена / ⏭ Пропустить — навигация в мастерах без ручного ввода команд (не тратят дневной лимит).",
    "👤 Я — ответственный / ✏️ Указать другого — выбор ответственного при создании мероприятия.",
    "✅ Оставить из шаблона / ✏️ Ввести своё — выбор названия и описания в быстром шаблоне.",
    "🗺️ Публикуем! — финальная публикация приключения после превью.",
    "📌 В основной чат / 📁 Тема — выбор места публикации в группе или forum topic.",
    "📆 За неделю / 🗓 За месяц / 🧾 За всё время — выбор периода для списков и дайджестов.",
    "✅ Присоединиться / 🚪 Выйти / 💸 Оплатил(а) / 🔄 Обновить / 🔒 Закрыть чек — управление чеком.",
    "✅ Подписаться на всё / 🚫 Отписаться от всего — подписки сохраняются автоматически.",
]


def build_donation_text() -> str:
    """Текст для команды /donate."""
    return "\n".join([
        *card_header("☕", "Поддержать бота", "Помоги оплачивать сервер и развитие"),
        *card_section("Зачем", [
            "Бот работает на арендованном сервере и требует постоянных расходов.",
            "Любая сумма помогает держать бота онлайн и развивать функции.",
        ]),
        *card_cta("Выбери удобный способ ниже — откроется страница сбора."),
    ])


def build_donation_unavailable_text() -> str:
    return "☕ Сборы для пожертвований пока не настроены. Напиши владельцу бота."


def build_main_menu_text(*, is_admin_or_owner: bool) -> str:
    """Компактный текст главного меню в ЛС."""
    season_icon = seasonal_menu_icon()
    season_label = seasonal_menu_label()
    lines = [
        *card_header(
            f"✨{season_icon}",
            "Центр приключений",
            f"{season_label} · {season_copy('tagline')}",
        ),
        f"<i>{brand_voice('menu_tagline')}</i>",
        *card_cta(brand_voice("menu_cta")),
    ]
    if is_admin_or_owner:
        lines.insert(-1, f"{BRAND['admin']} <i>Тебе доступен админ-раздел.</i>")
    return "\n".join(lines)


def build_notification_mode_text(*, current_mode: str) -> str:
    mode_label = MODE_LABELS.get(current_mode, MODE_LABELS["all"])
    tone = SECTION_TONES["notification_mode"]
    return "\n".join([
        *card_header(str(tone["icon"]), str(tone["title"]), str(tone["subtitle"])),
        f"Сейчас: <b>{escape(mode_label)}</b>",
        *card_section("Фокус", list(tone["focus"])),
        *card_cta(str(tone["cta"])),
    ])


def build_menu_section_text(
    section: str,
    *,
    is_admin_or_owner: bool,
    random_opted_in: bool | None = None,
) -> str | None:
    """Возвращает короткую карточку раздела главного меню."""
    if section == "admin" and not is_admin_or_owner:
        return None

    tone = SECTION_TONES.get(section)
    if not tone:
        return None

    focus = list(tone["focus"])
    if section == "community" and random_opted_in is not None:
        status = "участвуешь ✅" if random_opted_in else "не участвуешь"
        focus.insert(0, f"• Случайные встречи 1:1: <b>{status}</b>")

    return "\n".join([
        *card_header(str(tone["icon"]), str(tone["title"]), str(tone["subtitle"])),
        *card_section("Фокус", focus),
        *card_cta(str(tone["cta"])),
    ])


from bot.commands import COMMAND_SPECS, CommandKind, CommandSpec


HELP_GROUP_LABELS: dict[str, str] = {
    "base": "🚀 База",
    "events": "📅 Мероприятия",
    "digest": "📰 Дайджест и подписки",
    "community": "📈 Активность и встречи 1:1",
    "money": "💳 Скинуться",
    "admin": "🛡 Админ",
}

HELP_GROUP_ORDER: tuple[str, ...] = ("base", "events", "digest", "community", "money")


def _format_help_command_line(spec: CommandSpec) -> str:
    if spec.kind == CommandKind.HELP:
        return f"• <code>{spec.display_syntax}</code> — {spec.description}"
    return f"• /{spec.command} — {spec.description}"


COMMAND_ACTIONS = {
    spec.key: (spec.display_syntax, spec.description)
    for spec in COMMAND_SPECS
}

COMMAND_ACTIONS.update({
    "help": ("/help", "Подробная справка по ролям и сценариям."),
    "menu": ("/menu", "Главное кнопочное меню."),
    "status": ("/status", "Проверить, что бот онлайн."),
    "donate": ("/donate", "Поддержать работу бота — ссылки на сборы."),
    "create_event": ("/create_event", "Запустить мастер создания мероприятия."),
    "my_events": ("/my_events", "Открыть список твоих мероприятий."),
    "find_events": ("/find_events &lt;текст&gt;", "Поиск активных мероприятий. Пример: <code>/find_events квиз</code>"),
    "set_responsible": ("/set_responsible &lt;event_id&gt; &lt;user_id|@username&gt;", "Сменить ответственного. Пример: <code>/set_responsible 42 @ivan</code>"),
    "add_participant_manual": ("/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;", "Добавить участника вручную. Пример: <code>/add_participant_manual 42 @ivan</code>"),
    "set_carpool_manual": ("/set_carpool_manual &lt;event_id&gt; &lt;driver_id|@driver&gt; &lt;seats&gt;", "Ручное управление статусом карпулинга."),
    "add_passenger_manual": ("/add_passenger_manual &lt;event_id&gt; &lt;passenger_id|@passenger&gt; &lt;driver_id|@driver&gt;", "Ручное добавление пассажира к водителю."),
    "send_event_card": ("/send_event_card &lt;event_id&gt;", "Отправить короткое сообщение со ссылкой на основную карточку мероприятия."),
    "edit_event": ("/edit_event &lt;event_id&gt;", "Редактировать поля мероприятия (создатель, ответственный или админ). Пример: <code>/edit_event 42</code>"),
    "digest": ("/digest", "Открыть общую афишу."),
    "subscriptions": ("/subscriptions", "Настроить подписки и уведомления."),
    "my_digest": ("/my_digest", "Получить персональный дайджест."),
    "my_stats": ("/my_stats", "Посмотреть личную статистику участий."),
    "top": ("/top", "Показать топ активности за 30 дней."),
    "random_optin": ("/random_optin", "Включиться в случайные встречи 1:1."),
    "random_optout": ("/random_optout", "Выключиться из случайных встреч 1:1."),
    "birthday": ("/birthday", "Показать сохранённый день рождения."),
    "set_birthday": ("/set_birthday &lt;ДД.ММ&gt;", "Указать день рождения. Пример: <code>/set_birthday 15.07</code>"),
    "clear_birthday": ("/clear_birthday", "Удалить день рождения из профиля."),
    "split_bill": ("/split_bill", "Запустить мастер разделения чека."),
    "split_bill_add": ("/split_bill_add &lt;id&gt; &lt;user_id|@username&gt;", "Добавить участника в чек вручную."),
    "split_bill_remove": ("/split_bill_remove &lt;id&gt; &lt;user_id|@username&gt;", "Удалить участника из чека вручную."),
    "reset_user_limit": ("/reset_user_limit &lt;user_id|@username&gt;", "Сбросить дневной лимит команд участника. Пример: <code>/reset_user_limit @ivan</code>"),
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
        *card_header("⌨️", "Подсказка · команда", syntax.replace("&lt;", "<").replace("&gt;", ">")),
        *card_section("Что делает", [description]),
        *card_cta("Скопируй команду в чат или открой нужный раздел меню."),
    ])


def build_member_help_text() -> str:
    lines = ["ℹ️ <b>Команды участника</b>"]
    for group in HELP_GROUP_ORDER:
        specs = [spec for spec in COMMAND_SPECS if spec.group == group]
        if not specs:
            continue
        lines.append("")
        lines.append(HELP_GROUP_LABELS[group])
        lines.extend(_format_help_command_line(spec) for spec in specs)
    lines.extend(["", "🔘 <b>Описание кнопок</b>"])
    lines.extend(f"• {line}" for line in INLINE_BUTTON_HELP)
    return "\n".join(lines)


def build_admin_help_text() -> str:
    admin_specs = [spec for spec in COMMAND_SPECS if spec.group == "admin"]
    lines = ["<b>Админ · команды администратора/владельца</b>", ""]
    lines.extend(_format_help_command_line(spec) for spec in admin_specs)
    return "\n".join(lines)


def build_help_text(*, is_admin_or_owner: bool) -> str:
    member_help = build_member_help_text()
    if not is_admin_or_owner:
        return member_help
    return build_admin_help_text() + "\n" + member_help
