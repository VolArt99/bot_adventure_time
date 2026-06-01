from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote, quote_plus


def build_maps_link(location: str | None) -> str | None:
    """Возвращает ссылку Google Maps по текстовому адресу."""
    if not location:
        return None

    cleaned = location.strip()
    if not cleaned:
        return None

    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(cleaned)}"


def _clean_location(location: str | None) -> str | None:
    if not location:
        return None
    cleaned = location.strip()
    return cleaned or None


def build_yandex_navigator_link(location: str | None) -> str | None:
    """Возвращает HTTPS-ссылку поиска места в Яндекс Навигаторе."""
    cleaned = _clean_location(location)
    if not cleaned:
        return None
    return f"https://yandex.ru/navi/?text={quote_plus(cleaned)}"


def build_yandex_maps_link(location: str | None) -> str | None:
    """Возвращает HTTPS-ссылку поиска места именно в Яндекс Картах."""
    cleaned = _clean_location(location)
    if not cleaned:
        return None
    return f"https://yandex.ru/maps/?mode=search&text={quote_plus(cleaned)}"


def build_2gis_maps_link(location: str | None) -> str | None:
    if not location:
        return None
    cleaned = location.strip()
    if not cleaned:
        return None
    return f"https://2gis.ru/search/{quote_plus(cleaned)}"


def build_google_calendar_link(event: dict) -> str | None:
    """Возвращает ссылку на создание события в Google Calendar."""
    if not event:
        return None

    title = (event.get("title") or "Мероприятие").strip()
    date_time_raw = event.get("date_time")
    if not date_time_raw:
        return None

    try:
        start_dt = datetime.fromisoformat(str(date_time_raw))
    except ValueError:
        return None

    period_end_raw = event.get("period_end")
    if period_end_raw:
        try:
            end_dt = datetime.fromisoformat(str(period_end_raw))
        except ValueError:
            end_dt = None
        try:
            is_valid_end = bool(end_dt and end_dt > start_dt)
        except TypeError:
            is_valid_end = False
        if not is_valid_end:
            end_dt = None
    else:
        end_dt = None

    if end_dt is None:
        duration_minutes = int(event.get("duration_minutes") or 120)
        if duration_minutes <= 0:
            duration_minutes = 120
        end_dt = start_dt + timedelta(minutes=duration_minutes)

    dates = f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"
    description = (event.get("description") or "").strip()
    location = (event.get("location") or "").strip()

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
    }
    if description:
        params["details"] = description
    if location:
        params["location"] = location

    query = "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
    return f"https://calendar.google.com/calendar/render?{query}"


def build_yandex_calendar_link(event: dict) -> str | None:
    if not event:
        return None
    title = (event.get("title") or "Мероприятие").strip()
    date_time_raw = event.get("date_time")
    if not date_time_raw:
        return None
    try:
        start_dt = datetime.fromisoformat(str(date_time_raw))
    except ValueError:
        return None
    period_end_raw = event.get("period_end")
    end_dt = None
    if period_end_raw:
        try:
            end_dt = datetime.fromisoformat(str(period_end_raw))
        except ValueError:
            end_dt = None
    try:
        is_valid_end = bool(end_dt and end_dt > start_dt)
    except TypeError:
        is_valid_end = False
    if not is_valid_end:
        duration_minutes = int(event.get("duration_minutes") or 120)
        end_dt = start_dt + timedelta(minutes=max(1, duration_minutes))
    return (
        "https://calendar.yandex.ru/event?"
        f"name={quote_plus(title)}&start={quote_plus(start_dt.isoformat())}&end={quote_plus(end_dt.isoformat())}"
    )