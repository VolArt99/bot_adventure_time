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
}


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