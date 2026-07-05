from datetime import datetime
from typing import List, Dict
from html import escape
import pytz

from bot.config import TIMEZONE
from bot.constants import EVENT_CATEGORY_GROUPS, category_badge
from bot.utils.design import (
    BRAND,
    EVENT_CATEGORY_TONES,
    brand_voice,
    card_cta,
    card_progress_bar,
    card_section,
    season_copy,
    seasonal_card_divider,
    seasonal_menu_icon,
)
from bot.utils.event_links import (
    build_2gis_maps_link,
    build_google_calendar_link,
    build_maps_link,
    build_yandex_calendar_link,
    build_yandex_maps_link,
)

TZ = pytz.timezone(TIMEZONE)

GROUP_RULES_SHORT_TEXT = (
    "Наша цель — находить друзей и встречаться!\n\n"
    "✅ Делимся идеями, знакомимся, обсуждаем планы\n"
    "🚫 Политика, рознь, реклама без разрешения, флуд\n"
    "⚠️ Наказания: предупреждение → мут → бан\n"
    "📝 Разместите «Рассказ о себе» в теме группы\n"
    "👤 Укажите имя и фото (если ещё нет в Telegram)\n"
    "⏳ Срок — 7 дней с момента вступления"
)

GROUP_RULES_TEXT = (
    "Прежде чем вступить в группу, пожалуйста, ознакомься с правилами и целями.\n\n"
    "Наша цель: находить друзей и встречаться!\n\n"
    "В группе:\n"
    "💡 Делимся классными идеями, мыслями, историями!\n"
    "🎉 Обсуждаем всё!\n"
    "👋 Знакомимся!\n\n"
    "Что запрещено:\n"
    "🚫 Политика, ЛГБТ, религия, война, наркотики, нарушение законов РФ.\n"
    "🚫 Рознь, дискриминация, срач, оскорбления, троллинг, буллинг, чрезмерный флуд.\n"
    "🚫 Фейки, личка без разрешения, реклама без разрешения, удаление переписки с админами.\n\n"
    "Наказания за нарушения: Предупреждение -> Мут -> Бан.\n"
    "❓ Как выйти из бана? Свяжитесь с админом @Vol_Artem.\n"
    "Возврату не подлежат: наркоманы, провокаторы, агитаторы, сливщики.\n\n"
    "Обязательные правила:\n"
    "1️⃣ Разместить сообщение в подгруппе \"Рассказ о себе\" 📝.\n"
    "2️⃣ Указать настоящее имя и фото (если в профиле Telegram уже есть фото и имя — пункт опционален).\n"
    "3️⃣ Кратко написать, что вам интересно в рамках группы.\n"
    "4️⃣ Срок выполнения: 7 дней с момента вступления.\n\n"
    "📝 Администрация вправе менять правила."
)


def format_duration(minutes: int | None) -> str:
    if not minutes:
        return "не указана"

    hours = minutes // 60
    mins = minutes % 60

    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def format_event_period(start_dt: datetime, period_end_raw: str | None) -> str | None:
    """Форматирует период действия мероприятия, если он задан."""
    if not period_end_raw:
        return None
    try:
        end_dt = datetime.fromisoformat(str(period_end_raw)).astimezone(TZ)
    except ValueError:
        return None

    start_text = start_dt.strftime("%d.%m.%Y %H:%M")
    end_text = end_dt.strftime("%d.%m.%Y %H:%M")
    return f"📆 Период: {start_text} — {end_text}"


def category_to_hashtag(category: str | None) -> str:
    if not category:
        return ""
    safe = category.lower().replace(" ", "_")
    return f"#{safe}"


def category_emoji(category: str | None) -> str:
    """Возвращает emoji группы для категории."""
    if not category:
        return "🗂️"
    normalized = category.strip().lower()
    for group in EVENT_CATEGORY_GROUPS.values():
        if normalized in {str(item).lower() for item in group["subcategories"]}:
            return str(group["title"]).split()[0]
    return "🗂️"


def category_to_branded_hashtags(categories_raw: str | None) -> str:
    """Форматирует категории с едиными бейджами и хештегами."""
    if not categories_raw:
        return "не указана"
    categories = [item.strip() for item in categories_raw.split(",") if item.strip()]
    if not categories:
        return "не указана"
    return " ".join(f"{category_badge(category)} {category_to_hashtag(category)}" for category in categories)


def category_to_visual_badges(categories_raw: str | None) -> str:
    """Форматирует категории с цветовым бейджем группы и человекочитаемым названием."""
    if not categories_raw:
        return "⚪ 🗂️ Другое"
    categories = [item.strip() for item in categories_raw.split(",") if item.strip()]
    if not categories:
        return "⚪ 🗂️ Другое"

    visual_badges: list[str] = []
    for category in categories:
        normalized = category.lower()
        group_key = "other"
        for key, group in EVENT_CATEGORY_GROUPS.items():
            if normalized in {str(item).lower() for item in group["subcategories"]}:
                group_key = key
                break
        visual_badges.append(f"{EVENT_CATEGORY_TONES.get(group_key, '⚪')} {category_badge(category)}")
    return " ".join(visual_badges)


def category_to_hashtags(categories_raw: str | None) -> str:
    if not categories_raw:
        return "не указана"

    categories = [item.strip() for item in categories_raw.split(",") if item.strip()]
    if not categories:
        return "не указана"
    return " ".join(category_to_hashtag(category) for category in categories)


def event_status_badges(event: Dict, going_count: int, waitlist_count: int, *, now: datetime | None = None) -> str:
    """Возвращает визуальный статус карточки мероприятия."""
    try:
        dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    except (KeyError, ValueError):
        dt = None
    current_time = now.astimezone(TZ) if now else datetime.now(TZ)
    try:
        limit_value = int(event.get("participant_limit") or 0)
    except (TypeError, ValueError):
        limit_value = 0
    is_full = limit_value > 0 and going_count >= limit_value

    badges: list[str] = []
    if dt and dt >= current_time and (dt - current_time).total_seconds() <= 24 * 60 * 60:
        badges.append("🔥 скоро")
    if is_full and waitlist_count > 0:
        badges.append("⏳ резерв")
    elif is_full:
        badges.append("🚫 мест нет")
    else:
        badges.append("✅ набор открыт")
    return " · ".join(badges)


async def _resolve_weather_line(event: Dict, event_dt: datetime) -> str | None:
    """Погода: из БД или live-запрос в день мероприятия."""
    if event.get("weather_info"):
        return f"⛅ Погода: {escape(event['weather_info'])}"

    if event_dt.date() != datetime.now(TZ).date():
        return None

    location = (event.get("location") or "").strip()
    if not location:
        return None

    from bot.utils.weather import get_weather

    weather = await get_weather(city=location)
    if not weather:
        return None

    info = f"{weather['icon']} {weather['description']}, {weather['temp']}°C"
    return f"⛅ Погода сегодня: {escape(info)}"


async def format_event_message(
    event: Dict,
    going_list: List[int],
    waitlist_list: List[int],
    mentions_dict: Dict[int, str],
    topic_name: str | None = None,
    organizer_mention: str | None = None,
    responsible_mention: str | None = None,
    *,
    show_cta: bool = False,
    show_event_id: bool = False,
) -> str:
    dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    date_str = dt.strftime("%d.%m.%Y")
    time_str = dt.strftime("%H:%M")

    duration = format_duration(event.get("duration_minutes"))
    period_text = format_event_period(dt, event.get("period_end"))

    location = escape(event.get("location") or "не указано")
    title = escape(event["title"])
    description = escape(event.get("description") or "")
    category = escape(category_to_visual_badges(event.get("category")))

    price_total = event.get("price_total") or 0
    price_per_person = event.get("price_per_person") or 0
    going_count = len(going_list)
    waitlist_count = len(waitlist_list)
    limit_value = event.get("participant_limit")
    limit_str = str(limit_value) if limit_value else "∞"

    if price_total > 0 and going_count > 0:
        calculated_per_person = round(price_total / going_count, 2)
        price_detail = f"💰 ~{calculated_per_person} ₽/чел (общий счёт {price_total} ₽)"
    elif price_total > 0:
        price_detail = f"💰 общий счёт {price_total} ₽"
    elif price_per_person > 0:
        price_detail = f"💰 {price_per_person} ₽/чел"
    else:
        price_detail = "💰 Бесплатно"

    weather = await _resolve_weather_line(event, dt)
    carpool_enabled = bool(event.get("carpool_enabled"))

    going_inline = " · ".join(mentions_dict.get(uid, f"id{uid}") for uid in going_list) or "—"
    waitlist_inline = " · ".join(mentions_dict.get(uid, f"id{uid}") for uid in waitlist_list) or "—"

    status_badges = event_status_badges(event, going_count, waitlist_count)
    seat_bar = card_progress_bar(going_count, limit_value if limit_value else None)
    lines = [
        f"{BRAND['event']} <b>{title}</b>",
        status_badges,
        f"🎟 {seat_bar} {going_count}/{limit_str}",
        "",
        f"📅 {date_str}, {time_str}",
        f"📍 {location}",
    ]

    if description:
        lines.extend(["", description])

    about_lines: list[str] = [category]
    timing_parts = [f"⏱ {duration}", price_detail]
    about_lines.append(" · ".join(timing_parts))
    if period_text:
        about_lines.append(period_text)
    if carpool_enabled:
        about_lines.append("🚗 Карпулинг включён")
    if organizer_mention:
        about_lines.append(f"👤 Организатор: {organizer_mention}")
    if responsible_mention and responsible_mention != organizer_mention:
        about_lines.append(f"🧩 Ответственный: {responsible_mention}")
    if topic_name:
        about_lines.append(f"🚀 Тема: {escape(topic_name)}")
    if weather:
        about_lines.append(weather)
    if show_event_id:
        about_lines.append(f"🆔 ID: <code>{event['id']}</code>")
    lines.extend(card_section("О мероприятии", about_lines))

    lines.extend(card_section(f"Идут ({going_count})", [going_inline]))
    if waitlist_count > 0:
        lines.extend(card_section(f"Резерв ({waitlist_count})", [waitlist_inline]))

    maps_link = build_maps_link(event.get("location"))
    y_maps_link = build_yandex_maps_link(event.get("location"))
    dgis_link = build_2gis_maps_link(event.get("location"))
    gcal_link = build_google_calendar_link(event)
    ycal_link = build_yandex_calendar_link(event)
    link_parts: list[str] = []
    if maps_link:
        link_parts.append(f'<a href="{maps_link}">🗺 Карта</a>')
    if y_maps_link:
        link_parts.append(f'<a href="{y_maps_link}">Яндекс</a>')
    if dgis_link:
        link_parts.append(f'<a href="{dgis_link}">2ГИС</a>')
    if gcal_link:
        link_parts.append(f'<a href="{gcal_link}">📅 GCal</a>')
    if ycal_link:
        link_parts.append(f'<a href="{ycal_link}">📅 Я.Календарь</a>')
    if link_parts:
        lines.extend(card_section("🔗 Полезные ссылки", [" · ".join(link_parts)]))

    if carpool_enabled and str(event.get("id", "")).isdigit():
        from bot.database import get_drivers_with_passengers, get_ride_seekers

        drivers = await get_drivers_with_passengers(int(event["id"]))
        ride_seekers = await get_ride_seekers(int(event["id"]))
        if ride_seekers:
            seeker_line = " · ".join(
                mentions_dict.get(uid, f"id{uid}") for uid in ride_seekers
            )
            lines.extend(card_section(f"Ищут попутку ({len(ride_seekers)})", [seeker_line]))
        if drivers:
            lines.extend(card_section("🚗 Водители и пассажиры", []))
            for driver in drivers:
                driver_mention = mentions_dict.get(
                    driver["user_id"], f"id{driver['user_id']}"
                )
                free_seats = driver["car_seats"] - len(driver["passengers"])
                lines.append(
                    f"{driver_mention} — мест свободно: {free_seats}/{driver['car_seats']}"
                )
                if driver["passengers"]:
                    passengers = ", ".join(
                        mentions_dict.get(p, f"id{p}") for p in driver["passengers"]
                    )
                    lines.append(f"   Пассажиры: {passengers}")

    if show_cta:
        lines.extend(card_cta(brand_voice("event_card_cta")))
    return "\n".join(lines)


def format_digest_text(
    events: List[Dict], usernames_dict: Dict[int, str], period: str = "week"
) -> str:
    if not events:
        return brand_voice("empty_digest")

    period_title = {
        "week": "на неделю",
        "month": "на месяц",
        "all": "за всё время",
    }.get(period, "на выбранный период")

    lines = [
        f"<b>{seasonal_menu_icon()} {brand_voice('digest_title')} {period_title}</b>",
        f"<i>{season_copy('digest_intro')}</i>",
        seasonal_card_divider(),
        "",
    ]
    for e in events:
        dt = datetime.fromisoformat(e["date_time"]).astimezone(TZ)
        date_str = dt.strftime("%d.%m.%Y %H:%M")
        org_name = escape(usernames_dict.get(e["creator_id"], f"id{e['creator_id']}"))
        title = escape(e["title"])
        location = escape(e.get("location") or "не указано")
        topic_name = escape(e.get("topic_name") or "Основной чат")
        event_link = e.get("event_link")
        link_text = (
            f'<a href="{event_link}">открыть сообщение</a>'
            if event_link
            else "недоступна"
        )

        status_badges = event_status_badges(
            e,
            int(e.get("going_count") or 0),
            int(e.get("waitlist_count") or 0),
        )        
        lines.append(
            f"<b>{status_badges} · {title}</b>\n"
            f"🌍 Где: {location}\n"
            f"📅 Когда: {date_str}\n"
            f"🚀 Тема: {topic_name}\n"
            f"👤 Организатор: {org_name}\n"
            f"🔗 Ссылка: {link_text}\n"
        )

    lines.extend(["", f"<i>{brand_voice('afisha_iphone_hint_body')}</i>"])
    return "\n".join(lines)


def format_reminder_text(event: Dict, minutes_until: int) -> str:
    dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    date_str = dt.strftime("%d.%m.%Y %H:%M")
    title = escape(event["title"])
    location = escape(event.get("location") or "не указано")

    return (
        f"🔔 <b>Напоминание о мероприятии</b>\n\n"
        f"📌 {title}\n"
        f"📅 {date_str}\n"
        f"📍 {location}\n"
        f"⏰ Начинается через {minutes_until} мин"
    )


def format_attendance_prompt_text(event: Dict, hours_before: int) -> str:
    dt = datetime.fromisoformat(event["date_time"]).astimezone(TZ)
    date_str = dt.strftime("%d.%m.%Y %H:%M")
    title = escape(event["title"])
    location = escape(event.get("location") or "не указано")

    return (
        f"🗓 <b>Подтвердите участие</b>\n\n"
        f"Через ~{hours_before} ч стартует:\n"
        f"📌 <b>{title}</b>\n"
        f"📅 {date_str}\n"
        f"📍 {location}\n\n"
        f"Вы всё ещё идёте? Нажмите кнопку ниже — так организатор видит реальную явку."
    )
