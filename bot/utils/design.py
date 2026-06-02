"""Единый визуальный язык сообщений и карточек бота."""

from __future__ import annotations

from html import escape

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

VISUAL_GUIDE = {
    "card_header": "тон/иконка + жирный заголовок + короткий статус",
    "sections": "короткие блоки с единым разделителем и 3–6 строками",
    "cta": "последняя строка с явным следующим действием",
    "buttons": "главные CTA первыми, destructive-действия отдельно",
}


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


def card_progress_bar(current: int, total: int | None, *, width: int = 8) -> str:
    """Возвращает компактную текстовую шкалу прогресса для Telegram-карточек."""
    if total is None or total <= 0:
        return "░" * width

    ratio = max(0, min(1, current / total))
    filled_units = round(ratio * width)
    return f"{'█' * filled_units}{'░' * (width - filled_units)}"