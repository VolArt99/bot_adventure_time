"""Единый визуальный язык сообщений и карточек бота."""

from __future__ import annotations

from datetime import datetime
from html import escape

import pytz

from bot.config import TIMEZONE
from bot.constants import EVENT_CATEGORY_GROUPS

CARD_DIVIDER = "━━━━━━━━━━━━━━━━"
BRAND = {
    "event": "🎉",
    "money": "🧾",
    "notify": "🔔",
    "admin": "🛡",
    "community": "🤝",
    "help": "❓",
    "calendar": "📅",
    "onboarding": "🧭",
}

TONE_DOTS = {
    "event": "🟣",
    "money": "🟢",
    "notify": "🔵",
    "community": "🟠",
    "admin": "🔴",
    "help": "⚪",
    "onboarding": "🟡",
    "neutral": "⚪",
}

EVENT_CATEGORY_TONES = {
    "games": "🟣",
    "movie": "🟤",
    "sport": "🟢",
    "auto": "⚫",
    "travel": "🔵",
    "culture": "🟡",
    "study": "🟠",
    "food": "🔴",
    "social": "🟢",
    "other": "⚪",
}

SEASON_EMOJI = {
    "winter": "❄️",
    "spring": "🌸",
    "summer": "☀️",
    "autumn": "🍂",
}

SEASON_LABELS = {
    "winter": "Зима",
    "spring": "Весна",
    "summer": "Лето",
    "autumn": "Осень",
}

BRAND_VOICE = {
    "menu_tagline": "Куда отправимся сегодня?",
    "menu_cta": "Готов к приключению? Выбирай действие ниже.",
    "event_created": "Новое приключение опубликовано! 🗺️",
    "event_created_private": "🗺️ Приключение в пути! Карточка опубликована в группе.",
    "event_preview_intro": "👀 Вот что получилось — публикуем?",
    "event_card_cta": "Готов к приключению? · В путь · Резерв · В другой раз",
    "empty_digest": "📭 Тишина в Ланде Ооо… Запусти своё приключение через /create_event!",
    "digest_title": "Афиша приключений",
    "onboarding_welcome": (
        "Добро пожаловать в Adventure Time! 🗺️\n\n"
        "Здесь начинаются встречи и новые знакомства. Нажми «Старт», чтобы продолжить."
    ),
    "onboarding_rules_footer": "Готов(а)? Жми ❤️",
    "approved_member_start": (
        "Снова привет! 👋 Рад видеть тебя в Adventure Time.\n\n"
        "Доступ открыт — что дальше:\n"
        "1️⃣ Напиши о себе в теме «Рассказ о себе»\n"
        "2️⃣ Открой афишу через меню или /digest\n"
        "3️⃣ Запишись на ближайшую встречу\n\n"
        "Нажми кнопку ниже, чтобы открыть меню."
    ),
    "approval_welcome": "🎉🗺️ Дверь открыта! Добро пожаловать в команду приключений!",
    "approval_invite": "Ссылка для входа в группу:",
    "rules_accepted_member": "✅ Правила приняты — добро пожаловать в команду! 🎒",
    "rules_accepted_pending": "✅ Правила приняты. Заявка отправлена капитану на проверку. ⛵",
    "participation_join": "В путь! 🎒",
    "participation_waitlist": "В резерве — жду места ⏳",
    "participation_decline": "В другой раз 👋",
    "split_bill_created": "Чек собран — путь к расчёту открыт! 🧾",
    "empty_event_alert": "Пока никого нет — за сутки до старта список пуст.",
    "attendance_summary_title": "Сводка явки",
    "birthday_saved_hint": "В этот день мы поздравим вас в теме «Общение и не только» 🎂",
    "birthday_post_single": "🎂 <b>Сегодня день рождения!</b>",
    "birthday_post_many": "🎂 <b>Сегодня день рождения у {count} участников!</b>",
    "birthday_post_footer": "Поздравляем! Пусть день будет тёплым и весёлым ✨",
    "wizard_cancel": "Маршрут отменён — в другой раз! 🧭",
    "status_online": "✅ Компаньон на связи. Для карты возможностей — /help.",
    "afisha_iphone_hint_title": "📱 iPhone · ссылка «открыть сообщение» не срабатывает?",
    "afisha_iphone_hint_body": (
        "Перешлите это сообщение себе в «Избранное» — "
        "после этого переход на карточку должен сработать."
    ),
}

SEASON_COPY = {
    "winter": {
        "tagline": "Уютные встречи в холод",
        "digest_intro": "Зимняя афиша — горячий чай и настолки",
    },
    "spring": {
        "tagline": "Новые маршруты и знакомства",
        "digest_intro": "Весенняя афиша — прогулки и пробуждение",
    },
    "summer": {
        "tagline": "Длинные дни — больше приключений",
        "digest_intro": "Летняя афиша — пикники, поездки и спорт",
    },
    "autumn": {
        "tagline": "Тёплые вечера в компании",
        "digest_intro": "Осенняя афиша — кино, книги и уют",
    },
}

WIZARD_PROMPTS = {
    "title": "📝 Как назовём приключение?",
    "description": "📄 Расскажи подробнее (или «пропустить»):",
    "datetime": "🗓 Когда выдвигаемся?\n\nВыберите кнопку ниже или введите вручную:\n<b>ДД.ММ.ГГГГ ЧЧ:ММ</b>",
    "period_mode": "📆 Разовый поход или период действия?",
    "period_end": "🏁 Когда заканчивается период? Формат: ДД.ММ.ГГГГ ЧЧ:ММ",
    "duration": "⏱ Сколько длится маршрут? Минуты или «пропустить».",
    "location": "📍 Куда направимся? (или «пропустить»)",
    "price_mode": "💰 Как делим расходы на приключение?",
    "price_total": "💰 Общая сумма маршрута.\nПример: 5000",
    "price_person": "💰 Сколько с человека?\nПример: 500",
    "limit": "👥 Сколько искателей приключений? Число, «без лимита» или «пропустить».",
    "thread": "🗂 Куда опубликуем карточку?",
    "category_group": "📂 Выбери направление приключения:",
    "category_sub": "📂 Уточни категории (можно несколько):",
    "preview_intro": "👀 <b>Мини-превью карточки</b>\nПроверь, как приключение будет выглядеть в группе.",
}

VISUAL_GUIDE = {
    "card_header": "тон/иконка + жирный заголовок + короткий статус",
    "sections": "короткие блоки с единым разделителем и 3–6 строками",
    "cta": "последняя строка с явным следующим действием",
    "buttons": "главные CTA первыми, destructive-действия отдельно",
}


def primary_category_group(categories_raw: str | None) -> str:
    """Возвращает ключ основной группы категории для визуального акцента."""
    if not categories_raw:
        return "other"
    categories = [item.strip() for item in categories_raw.split(",") if item.strip()]
    if not categories:
        return "other"
    normalized = categories[0].lower()
    for key, group in EVENT_CATEGORY_GROUPS.items():
        if normalized in {str(item).lower() for item in group["subcategories"]}:
            return key
    return "other"


def category_accent_strip(categories_raw: str | None, *, width: int = 4) -> str:
    """Цветовая полоска-акцент слева от карточки по категории."""
    group_key = primary_category_group(categories_raw)
    block = EVENT_CATEGORY_TONES.get(group_key, TONE_DOTS["neutral"])
    return block * width


def current_season() -> str:
    """Текущий сезон по календарю и таймзоне бота."""
    month = datetime.now(pytz.timezone(TIMEZONE)).month
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "autumn"


def seasonal_menu_icon() -> str:
    """Сезонный эмодзи для шапки меню."""
    return SEASON_EMOJI[current_season()]


def seasonal_menu_label() -> str:
    """Человекочитаемая подпись текущего сезона."""
    return SEASON_LABELS[current_season()]


def brand_voice(key: str) -> str:
    """Возвращает фирменную фразу по ключу."""
    return BRAND_VOICE[key]


def season_copy(key: str) -> str:
    """Сезонный текст (tagline, digest_intro и т.д.)."""
    return SEASON_COPY[current_season()][key]


def seasonal_card_divider() -> str:
    """Сезонный разделитель для карточек и меню."""
    return f"═ {seasonal_menu_icon()} ═"


def wizard_prompt(prompt_key: str) -> str:
    """Текст шага мастера создания мероприятия."""
    return WIZARD_PROMPTS[prompt_key]


def tone_badge(tone: str, label: str) -> str:
    """Возвращает цветовой бейдж для карточек и меню."""
    dot = TONE_DOTS.get(tone, TONE_DOTS["neutral"])
    return f"{dot} {escape(label)}"


def step_badge(step: int, total: int, title: str) -> str:
    """Единый progress-заголовок для onboarding и wizard-сценариев."""
    return f"{BRAND['onboarding']} Шаг {int(step)}/{int(total)} · {escape(title)}"


def card_header(icon: str, title: str, subtitle: str | None = None) -> list[str]:
    """Возвращает единый заголовок карточки."""
    lines = [f"{icon} <b>{escape(title)}</b>"]
    if subtitle:
        lines.append(f"<i>{escape(subtitle)}</i>")
    lines.append(CARD_DIVIDER)
    return lines


def card_section(title: str, lines: list[str]) -> list[str]:
    """Форматирует секцию карточки с одинаковым разделителем."""
    return ["", f"<b>{title}</b>", *lines]


def compact_cta(primary: str, secondary: str | None = None) -> str:
    """Короткий CTA-текст для карточек, где Telegram-кнопки уже видны ниже."""
    if secondary:
        return f"{primary} · {secondary}"
    return primary


def card_cta(text: str) -> list[str]:
    """Форматирует CTA-блок в конце карточки."""
    return ["", CARD_DIVIDER, f"👉 <i>{escape(text)}</i>"]


def card_progress_bar(current: int | float, total: int | float | None, *, width: int = 8) -> str:
    """Возвращает компактную текстовую шкалу прогресса для Telegram-карточек."""
    if total is None or total <= 0:
        return "░" * width

    ratio = max(0, min(1, float(current) / float(total)))
    filled_units = round(ratio * width)
    return f"{'█' * filled_units}{'░' * (width - filled_units)}"


def money_collection_line(collected: float, total: float, *, width: int = 8) -> str:
    """Шкала сбора денег: ████░░░░ 1200/3000 ₽."""
    bar = card_progress_bar(collected, total, width=width)
    return f"{bar} {collected:.0f}/{total:.0f} ₽"
