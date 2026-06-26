"""Константы и справочники бота."""

EVENT_CATEGORY_GROUPS: dict[str, dict[str, list[str] | str]] = {
    "games": {
        "title": "🎲 Игры и соревнования",
        "subcategories": [
            "игры",
            "настолки",
            "интеллектуальные игры",
            "викторины",
            "своя игра",
            "ПК игры",
            "консольные игры",
            "квесты",
        ],
    },
    "movie": {
        "title": "🎬 Кино и видео",
        "subcategories": ["кино", "совместные просмотры", "киновечер"],
    },
    "sport": {
        "title": "💪 Спорт и активный отдых",
        "subcategories": [
            "спорт",
            "активный отдых",
            "спорт на свежем воздухе",
            "активные игры",
            "прогулки",
            "велопрогулки",
            "велопокатушки",
            "картинг",
        ],
    },
    "auto": {
        "title": "🚗 Авто и техника",
        "subcategories": ["машина", "автомобили", "автоспорт", "формула 1"],
    },
    "travel": {
        "title": "✈️ Путешествия и приключения",
        "subcategories": [
            "путешествия",
            "поездки",
            "дальние поездки",
            "походы",
            "тревел",
            "выезды на природу",
            "экскурсии",
        ],
    },
    "culture": {
        "title": "🎭 Культура и творчество",
        "subcategories": ["культура", "театры", "музеи", "выставки", "творчество", "танцы", "музыка"],
    },
    "study": {
        "title": "📚 Книги и обучение",
        "subcategories": [
            "книги",
            "книжный клуб",
            "обсуждение книг",
            "обучение",
            "саморазвитие",
            "психология",
            "астрономия",
        ],
    },
    "food": {
        "title": "🍔 Еда и гастрономия",
        "subcategories": ["еда", "гастрономия", "пикники", "шашлыки", "природа", "рестораны", "кафе"],
    },
    "social": {
        "title": "💬 Общение и знакомства",
        "subcategories": [
            "общение",
            "живое общение",
            "ламповое общение",
            "душевные встречи",
            "знакомства",
            "новые друзья",
            "тусовки",
            "вечеринки",
            "чат",
            "флудилка",
            "юмор",
        ],
    },
    "other": {
        "title": "🗓 Организация и впечатления",
        "subcategories": [
            "мероприятия",
            "календарь событий",
            "спонтанные встречи",
            "здесь и сейчас",
            "фотоотчеты",
            "впечатления",
            "досуг",
            "хобби",
        ],
    },
}

EVENT_CATEGORIES: list[str] = [
    subcategory
    for group in EVENT_CATEGORY_GROUPS.values()
    for subcategory in group["subcategories"]
]

CATEGORY_BADGES: dict[str, set[str]] = {
    "🎲 Настолки": {"настолки", "настольные игры", "игры"},
    "📚 Книги": {"книги", "книжный клуб", "обсуждение книг"},
    "🚶 Прогулки": {"прогулки", "велопрогулки", "спонтанные встречи"},
    "🍽 Еда": {"еда", "гастрономия", "пикники", "шашлыки", "рестораны", "кафе"},
    "🧠 Квиз": {"квиз", "квизы", "викторины", "интеллектуальные игры", "своя игра"},
}


def category_badge(category: str | None) -> str:
    """Возвращает единый человекочитаемый бейдж категории."""
    normalized = (category or "").strip().lower()
    if not normalized:
        return "📂 Другое"
    for badge, aliases in CATEGORY_BADGES.items():
        if normalized in aliases:
            return badge
    return f"{category.strip().title()}"


def category_badge_key(category: str | None) -> str:
    """Ключ для дедупликации подкатегорий с одинаковым бейджем."""
    return category_badge(category).casefold()


def dedupe_categories(categories: list[str]) -> list[str]:
    """Убирает дубли подкатегорий (в т.ч. с одинаковым бейджем)."""
    seen_exact: set[str] = set()
    seen_badges: set[str] = set()
    result: list[str] = []
    for category in categories:
        normalized = (category or "").strip()
        if not normalized or normalized in seen_exact:
            continue
        badge_key = category_badge_key(normalized)
        if badge_key in seen_badges:
            continue
        seen_exact.add(normalized)
        seen_badges.add(badge_key)
        result.append(normalized)
    return result

CARPOOL_HELP_TEXT = (
    "🚗 <b>Нужен карпулинг?</b> (да/нет)\n"
    "Карпулинг — это когда участники едут вместе на машине.\n"
    "• «Еду на машине» — становитесь водителем и указываете места.\n"
    "• «Ищу попутку» — выбираете водителя со свободными местами."
)
