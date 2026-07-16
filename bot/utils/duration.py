"""Парсинг длительности мероприятия из свободного текста."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HOUR_UNIT = r"(?:ч|час|часа|часов|h|hr|hrs)"
_MIN_UNIT = r"(?:м|мин|минута|минуты|минут|min|mins)"


@dataclass(frozen=True)
class DurationParseResult:
    """Результат разбора длительности."""

    minutes: int | None = None
    needs_unit: bool = False
    raw_value: float | None = None
    error: str | None = None


def parse_duration_text(text: str) -> DurationParseResult:
    """
    Разбирает длительность.

    Поддерживает:
    - «1 ч 30 мин», «1ч 30м», «1.5 ч», «90 мин»
    - голое число → needs_unit=True (уточнить часы/минуты)
    - «пропустить» / «-» → minutes=None
    """
    raw = (text or "").strip().lower().replace(",", ".")
    if not raw:
        return DurationParseResult(error="empty")
    if raw in {"пропустить", "skip", "-"}:
        return DurationParseResult(minutes=None)

    matched = re.fullmatch(
        rf"(\d+(?:\.\d+)?)\s*{_HOUR_UNIT}\s*(\d+(?:\.\d+)?)\s*{_MIN_UNIT}",
        raw,
    )
    if matched:
        hours = float(matched.group(1))
        mins = float(matched.group(2))
        total = int(round(hours * 60 + mins))
        if total <= 0:
            return DurationParseResult(error="non_positive")
        return DurationParseResult(minutes=total)

    matched = re.fullmatch(rf"(\d+(?:\.\d+)?)\s*{_HOUR_UNIT}", raw)
    if matched:
        total = int(round(float(matched.group(1)) * 60))
        if total <= 0:
            return DurationParseResult(error="non_positive")
        return DurationParseResult(minutes=total)

    matched = re.fullmatch(rf"(\d+(?:\.\d+)?)\s*{_MIN_UNIT}", raw)
    if matched:
        total = int(round(float(matched.group(1))))
        if total <= 0:
            return DurationParseResult(error="non_positive")
        return DurationParseResult(minutes=total)

    matched = re.fullmatch(r"(\d+(?:\.\d+)?)", raw)
    if matched:
        value = float(matched.group(1))
        if value <= 0:
            return DurationParseResult(error="non_positive")
        return DurationParseResult(needs_unit=True, raw_value=value)

    return DurationParseResult(error="bad_format")


def apply_duration_unit(raw_value: float, unit: str) -> int | None:
    """Переводит голое число в минуты по выбранной единице (hours|minutes)."""
    if raw_value <= 0:
        return None
    if unit == "hours":
        return int(round(raw_value * 60))
    if unit == "minutes":
        return int(round(raw_value))
    return None


DURATION_HINT = (
    "Примеры: <b>1 ч 30 мин</b>, <b>90 мин</b>, <b>2</b> "
    "(для числа без единиц бот уточнит: часы или минуты)"
)
