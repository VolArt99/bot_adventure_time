# Bot Adventure Time

Telegram-бот для приватного сообщества: мероприятия, участие, напоминания, дайджесты, random 1:1 встречи, онбординг новых участников и разделение чеков.


---

## Зачем нужен этот репозиторий

Проект автоматизирует рутину админов и организаторов:
- создание и публикация мероприятий в Telegram-темах (Topics);
- учёт участников (основной список + резерв);
- напоминания о событиях;
- дайджесты для группы и персональные дайджесты;
- доступ по ролям и базовый онбординг новых пользователей;
- вспомогательные сценарии вроде random-встреч 1:1 и split bill.

Если вы только открыли проект: начните с разделов **«Архитектура»**, **«Структура репозитория»**, **«Запуск»** и **«Команды»**.

---

## Технологический стек

- **Python 3.10+**
- **aiogram 3.x**
- **PostgreSQL 16**
- **APScheduler**
- **Docker Compose** (рекомендуемый деплой на VDS)
- Опционально: **OpenWeatherMap** для погоды

---

## Архитектура (кратко)

### Входные точки
- **VDS / локально (рекомендуется):** `python -m bot.main` или `docker compose up -d`

### Основной поток
1. Telegram update поступает в `bot.main`.
2. `Dispatcher` пропускает update через middleware/фильтры.
3. Нужный handler выполняет бизнес-логику.
4. Данные читаются/пишутся через `bot.database` → `bot.database_pg`.
5. Для событий и уведомлений могут ставиться задания в APScheduler.

### Хранение состояния
- FSM хранится в таблице `fsm_states` (PostgreSQL), чтобы сценарии не терялись при рестартах.

---

## Структура репозитория (подробно)

```text
.
├── docker-compose.yml
├── Dockerfile
├── deploy/
│   ├── deploy.sh
│   ├── backup_db.sh
│   ├── bot-adventure-time.service
│   ├── postgresql.vds.conf
│   ├── server_hardening.example.sh
│   └── VDS_SETUP.md
├── requirements.txt
├── промт.txt
├── README.md
├── tests/
│   ├── test_access_and_flows.py
│   ├── test_help_text_html.py
│   ├── test_texts.py
│   ├── test_fsm_storage_pg.py
│   ├── test_db_pool.py
│   └── … (см. `tests/test_*.py`)
└── bot/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── init_flags.py
    ├── constants.py
    ├── topics_config.py
    ├── texts.py
    ├── keyboards.py
    ├── check_env.py
    ├── database.py
    ├── database_pg.py
    ├── db_pool.py
    ├── fsm_storage_pg.py
    ├── middleware/
    │   ├── __init__.py
    │   ├── command_access.py
    │   ├── topic_discoverer.py
    │   └── latency_metrics.py
    ├── filters/
    │   ├── __init__.py
    │   ├── admin.py
    │   ├── command_access.py
    │   └── registered_user.py
    ├── handlers/
    │   ├── __init__.py
    │   ├── common_feature/            # структурный модуль common: handlers/views/services
    │   ├── events.py
    │   ├── participation.py
    │   ├── my_events.py
    │   ├── digest.py
    │   ├── subscriptions.py
    │   ├── roadmap.py
    │   ├── split_bill_feature/        # структурный модуль split_bill: handlers/views/services
    │   ├── admin.py
    │   └── event_scenarios/
    │       ├── __init__.py
    │       ├── shared.py
    │       ├── create.py
    │       ├── edit.py
    │       ├── cancel.py
    │       ├── category.py
    │       └── carpool.py
    ├── commands.py                # единый реестр команд
    ├── db_pool.py
    ├── fsm_storage_pg.py
    └── utils/
        ├── __init__.py
        ├── design.py              # BRAND_VOICE, SEASON_COPY, визуальные primitives
        ├── scheduler.py
        ├── weather.py
        ├── metrics.py
        ├── topics.py
        ├── event_links.py
        ├── helpers.py
        └── pairing.py
```

> Полный список тестов: `tests/test_*.py` (тексты, доступы, FSM PG, pool, callbacks и др.).

### Что где находится и за что отвечает

#### Корень проекта
- `docker-compose.yml` — postgres + bot, лимиты RAM, тюнинг PG.
- `deploy/postgresql.vds.conf` — настройки PostgreSQL для 2 ГиБ RAM.
- `deploy/VDS_SETUP.md` — пошаговая настройка VDS.
- `requirements.txt` — зависимости (`bot/requirements.txt`).
- `.env.example` — безопасный шаблон переменных окружения без секретов.
- `README.md` — этот документ.
- `промт.txt` — проектный технический промт/guide для разработки.

#### `bot/main.py`
- Инициализация бота, dispatcher, FSM storage.
- Регистрация роутеров и middleware.
- Режим polling.
- Ленивая инициализация БД/тем/планировщика.
- Глобальный error-handler с уведомлением владельца в ЛС и троттлингом повторов ошибок.

#### `bot/config.py`
- Чтение env-переменных.
- Роли/лимиты/набор разрешённых команд.
- Таймзона и параметры дайджеста/напоминаний.

#### `bot/database_pg.py`
- Создание схемы PostgreSQL.
- Все CRUD-операции по событиям, участникам, темам, random 1:1, split bill и т.д.
- Агрегации/отчёты/поисковые запросы.

#### `bot/handlers/`
- `common_feature/handlers.py` — `/start`, `/help`, `/menu`, `/status`, `/donate`, onboarding, owner approve/reject, служебные команды.
- `common_feature/services.py` — проверка участия в группе, notify owner и т.д.
- `common_feature/views.py` — help, menu, onboarding-тексты (через `brand_voice` / `season_copy`).
- `events.py` + `event_scenarios/*` — FSM создания/редактирования/категоризации событий.
- `participation.py` — кнопки участия (в путь / резерв / в другой раз, карпулинг).
- `split_bill_feature/handlers.py` — FSM и callback-хендлеры split bill.
- `split_bill_feature/services.py` — формат карточки, шкала сбора, чек-лист оплат.
- `roadmap.py` — статистика, top, find, random optin/optout/pairs.
- `digest.py`, `subscriptions.py`, `my_events.py`, `admin.py` — профильные сценарии.

#### `bot/utils/design.py`
- Единый визуальный язык: `BRAND_VOICE`, `SEASON_COPY`, `WIZARD_PROMPTS`.
- Хелперы: `brand_voice()`, `season_copy()`, `category_accent_strip()`, `card_progress_bar()`, `money_collection_line()`.
- Сезонная шапка меню и дайджеста (зима / весна / лето / осень).

#### `bot/middleware/`
- `command_access.py` — role-based доступ и лимиты команд.
- `topic_discoverer.py` — автообновление справочника тем по входящим апдейтам.
- `latency_metrics.py` — сбор времени обработки update (p50/p95/p99 через периодические логи).

#### `bot/filters/`
- Фильтры прав (admin/registered/restricted command).

#### `bot/utils/`
- `scheduler.py` — постановка/восстановление напоминаний и периодических задач.
- `weather.py` — интеграция с погодой, HTTP session reuse, TTL-кеш и rate-limit.
- `metrics.py` — лёгкий in-memory сбор latency-метрик (p50/p95/p99).
- `event_links.py` — карты и календарные ссылки (Google/Яндекс).
- `helpers.py` — mention/username/ссылки на сообщения (`build_event_message_link` с поддержкой `thread_id` для Topics).
- `pairing.py` — алгоритм random-пар 1:1.

#### `tests/`
- Unit-тесты: тексты и брендинг, HTML-экранирование, доступы, FSM storage PG, pool, callbacks, scheduler.

---

## Команды бота

> Реестр команд: `bot/commands.py`. Доступность зависит от роли (`OWNER_ID`, `ADMIN_IDS`, approved-member) и лимитов из `config.py`.

### Базовые
- `/start` — вход/онбординг; для одобренного участника — приветствие и кнопка перехода в `/menu`.
- `/help` — подробная справка без прикреплённого меню.
- `/menu` — Control Center с разделами 🎉 События, 🧾 Деньги, 🔔 Уведомления, 🤝 Комьюнити (+ админ для админов).
- `/status` — быстрая проверка, что бот онлайн.
- `/donate` — ссылки на сборы (Сбербанк / Т-Банк) в ЛС; доступна и не-участникам (`OUTSIDER_ALLOWED_COMMANDS=start,donate`).

### Мероприятия
- `/create_event` — пошаговое создание события (в т.ч. выбор формата цены: общая/с человека/бесплатно; место проведения можно пропустить кнопкой).
- `/my_events` — ваши события.
- `<code>/find_events &lt;запрос&gt;</code>` — поиск по активным событиям.
- `<code>/edit_event &lt;event_id&gt;</code>` — редактирование полей карточки (создатель, ответственный или админ).
- `<code>/set_responsible &lt;event_id&gt; &lt;user_id|@username&gt;</code>` — сменить ответственного (создатель/админ).
- `<code>/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;</code>` — ручное добавление участника.
- `<code>/send_event_card &lt;event_id&gt;</code>` — отправить короткое сообщение со ссылкой на основную карточку мероприятия (организатор/ответственный/админ).
- `<code>/set_carpool_manual &lt;event_id&gt; &lt;driver_id|@username&gt; &lt;seats&gt;</code>` — назначить водителя и количество мест.
- `<code>/add_passenger_manual &lt;event_id&gt; &lt;passenger_id|@passenger&gt; &lt;driver_id|@driver&gt;</code>` — ручное назначение пассажира.

### Дайджесты
- `/digest` — общий дайджест.
- `/subscriptions` — подписки.
- `/my_digest` — персональная подборка.

### Активность
- `/my_stats` — личная статистика.
- `/top` — топ участников.

### Random 1:1
- `/random_optin` — включиться в random-пулы.
- `/random_optout` — выключиться из random-пулов.
- `/random_pairs` — (admin) формирование пар с выбором группы/подгруппы для публикации общей карточки.
- `/random_optin_count` — (owner) количество согласных на 1:1.

### Split bill
- `/split_bill` — пошаговый сценарий создания чека (с выбором исходного мероприятия и подгруппы публикации).
- В сценарии `/split_bill` теперь запрашиваются реквизиты перевода:
  - формат (телефон / карта / ссылка),
  - банк (Сбер / Т-банк / Альфа / Яндекс / свой вариант),
  - ФИО получателя.
- Управление присоединением/оплатой/статусом/закрытием делается кнопками в карточке чека.
- `/split_bill_add <id> <user_id|@username>` / `/split_bill_remove <id> <user_id>` — ручное управление участниками.

### Сервисные/админские
- `/roles`, `/usage_stats`, `/debug_info`, `/list_topics`, `/update_topic_names`, `/admin_report`, `/pending_intro`, `/send_events_list`, `/member_reengage`, `/sync_members`.

### UX и визуальное оформление
- Тон голоса бота — приключенческий (Adventure Time community), без копирования персонажей мультсериала. Тексты централизованы в `bot/utils/design.py` (`BRAND_VOICE`, `SEASON_COPY`, `WIZARD_PROMPTS`).
- `/menu` — сезонная шапка (❄️/🌸/☀️/🍂), слоган «Куда отправимся сегодня?», разделитель `═ emoji ═`.
- Кнопки участия в карточке: `✅ В путь!` / `⏳ В резерве` / `❌ В другой раз`.
- Карточка мероприятия (layout **Hero + детали**): шапка с названием, статусом и местами; дата и локация отдельными строками; блок «О мероприятии» (категории, длительность, стоимость — один раз); списки «Идут (N)» и «Резерв»; погода в день события (`WEATHER_API_KEY`).
- Дайджест: «Афиша приключений» + сезонное интро; пустой период — «Тишина в Ланде Ооо…».
- Split-bill: шкала сбора `████░░░░ 1500/3000 ₽` + чек-лист оплат ✅/⏳.
- Онбординг: при одобрении заявки — текст `🎉🗺️ Дверь открыта!` (без стикера); владелец получает уведомление, когда участник с pending-интро запускает `/start`.
- Мастер событий: прогресс `Шаг 7/12 · 📍 Маршрут`, превью с кнопкой `🗺️ Публикуем!`, «↩️ Назад» на всех ключевых шагах (включая тему, категории и превью).
- Быстрые шаблоны в `/menu`: спорт, язык, еда, кино, астрономия, лекция, картинг, кооп на ПК, книжный клуб, квиз, настолки, прогулка — с выбором «оставить из шаблона» или «ввести своё» для названия и описания.
- Категории: единые бейджи без дублей в UI; дедупликация при выборе подкатегорий.
- Статусы карточки: 🔥 скоро, ✅ набор открыт, ⏳ резерв, 🚫 мест нет.
- Мастера поддерживают «↩️ Назад» на ключевых шагах.

### Важные детали поведения
- `/pending_intro` — единая команда контроля «Рассказа о себе»: показывает pending-участников (с кнопками отметки) и сводный статус по всем актуальным участникам группы.
- В командах, где оператор задаёт `user_id` вручную (`/set_responsible`, `/add_participant_manual`, `/split_bill_add`), применяется проверка «только актуальные участники группы». Для `@username` используется поиск в БД и fallback по approved members через Telegram API.
- Для random 1:1 в пулы и пары попадают только пользователи из `approved_members` (исключённые участники автоматически не участвуют). `/random_pairs` публикует общую карточку в выбранную группу/подгруппу и не рассылает личные уведомления о парах.
- `/send_event_card` публикует короткое сообщение со ссылкой на основную карточку мероприятия, а не вторую интерактивную карточку; callback-кнопки продолжают обновлять только основную карточку.
- `/digest` и `/my_digest` используют ссылки на основные карточки мероприятий, если у события сохранён `message_id`.
- В афише, дайджестах и `/send_events_list` учитываются мероприятия с **периодом действия** (`period_end`): если период ещё не закончился, событие попадает в список даже при старте в прошлом.
- Ссылки на карточки в форумных темах строятся как `t.me/c/<chat>/<thread>/<message>` (нужен `thread_id`); без него iOS-клиент Telegram часто открывает только группу.
- В split-bill сценарии (`/split_bill`) промежуточные сообщения в ЛС удаляются, чтобы не засорять диалог; обычные меню/карточки не удаляются без явной wizard-политики.
- Владелец получает технические алерты о необработанных ошибках бота в ЛС (с защитой от спама повторяющимися ошибками).

> `/send_events_list` публикует карточки с ссылками на исходные сообщения мероприятий (если у событий сохранён `message_id` и `thread_id` для тем форума).

---

## Переменные окружения

Шаблон: `.env.example`. Для Docker Compose также нужен `POSTGRES_PASSWORD`.

### Обязательные
- `BOT_TOKEN`
- `GROUP_ID`
- `POSTGRES_PASSWORD` (при деплое через Docker Compose)
- `DATABASE_URL` (или `PGHOST` / `PGUSER` / `PGPASSWORD` / `PGDATABASE`)

### Обычно нужны
- `OWNER_ID`
- `ADMIN_IDS` (через запятую)
- `OWNER_CONTACT` — `@username`, HTTPS-ссылка или текст; в одобрении заявки отображается как кликабельный контакт
- `ENV=production`
- `TIMEZONE` — по умолчанию `Europe/Moscow` (даты в боте, дайджест, напоминания). Часовой пояс ОС на VDS в Финляндии: `Europe/Helsinki` (`timedatectl`), см. `deploy/VDS_SETUP.md`
- `AUTO_INIT_DB=1` — создать/проверить схему при старте

### Опциональные
- `WEATHER_API_KEY` — OpenWeatherMap; погода при создании события и в день мероприятия
- `DONATION_SBERBANK_URL`, `DONATION_TBANK_URL` — ссылки для `/donate`
- `OUTSIDER_ALLOWED_COMMANDS` — по умолчанию `start,donate`
- `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE` — пул PostgreSQL (по умолчанию 1/5, оптимально для 2 ГиБ RAM)
- `DIGEST_DAY_OF_WEEK`, `DIGEST_HOUR` — расписание weekly digest
- Лимиты и списки команд — см. `config.py`

### Производительность и безопасность
- `aiohttp>=3.13.4` — закрыты известные DoS/header parser уязвимости
- Погодный клиент: TTL-кеш 300 с, rate-limit 2 с на ключ (задано в `bot/utils/weather.py`)
- PostgreSQL на VDS: тюнинг в `deploy/postgresql.vds.conf`, подключается через `docker-compose.yml`

---

## Локальный запуск

### Установка
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Проверка окружения
```bash
python -m bot.check_env
```

### Запуск бота (polling)
```bash
python -m bot.main
```

---

## Тестирование и проверки

```bash
pytest -q
python -m compileall -q bot tests
```

Рекомендуется прогонять минимум `pytest -q` перед каждым PR.

---

## Безопасность и эксплуатационные практики

- Не храните ключи/токены в репозитории; используйте секреты CI/CD и env-переменные.
- Для PostgreSQL используйте параметризованные запросы через asyncpg pool.
- Ограничения команд и ролей централизованы в `middleware/command_access.py` и `config.py`.
- При изменении команд/доступов синхронизируйте:
  1) `/help` тексты,  
  2) README,  
  3) `промт.txt`.

---

## Что обновилось в последних изменениях

- **Афиша и дайджесты:** мероприятия с периодом действия (`period_end`) попадают в списки, пока период не закончился; ссылки на карточки в темах форума включают `thread_id` (исправление deep-link на iOS).
- **VDS-деплой:** Docker Compose + PostgreSQL 16, polling, тюнинг PG для 2 ГиБ RAM, лимиты памяти контейнеров.
- **Удалён legacy:** YDB, Cloud Functions/webhook, `dynamic_handler.py`, codegen из YDB.
- **Брендинг:** `BRAND_VOICE` / `SEASON_COPY` в `design.py`; приключенческий тон в меню, онбординге, мастерах, дайджесте.
- **`/donate`:** кнопки-ссылки на сборы Сбербанка и Т-Банка.
- **Карточки:** цветовая полоска категории, progress bar мест, погода в день события, сезонная шапка меню.
- **Split-bill:** шкала сбора средств + чек-лист оплат.
- **Участие:** кнопки «В путь!» / «В резерве» / «В другой раз».
- **Онбординг:** при одобрении — приветственный текст с эмодзи (без стикера).
- Документация по настройке сервера: `deploy/VDS_SETUP.md`.

---

## Визуальный стиль

Все пользовательские тексты и карточки строятся через `bot/utils/design.py`:

| Словарь / функция | Назначение |
|-------------------|------------|
| `BRAND_VOICE` | Фразы бота: меню, онбординг, участие, статусы |
| `SEASON_COPY` | Сезонные слоганы и интро дайджеста |
| `WIZARD_PROMPTS` | Тексты шагов мастера создания события |
| `brand_voice(key)` | Получить фразу по ключу |
| `season_copy(key)` | Сезонный текст (tagline, digest_intro) |
| `category_accent_strip()` | Цветовая полоска категории на карточке |
| `card_progress_bar()` | Текстовая шкала прогресса |
| `money_collection_line()` | Шкала сбора денег в split-bill |

**Правило для разработчиков:** новые пользовательские фразы добавлять в `BRAND_VOICE` / `WIZARD_PROMPTS`, а не хардкодить в handlers.

Карточка мероприятия: layout **Hero + детали** (шапка → описание → «О мероприятии» → участники), погода в день события (`WEATHER_API_KEY`), CTA «Готов к приключению?».

Split-bill: блоки «Сбор средств» и «Чек-лист оплат».

---

## Безопасность

- Минимальная версия `aiohttp` — `3.13.4`: это закрывает известные проблемы с multipart DoS, zip bomb DoS и обработкой небезопасных response headers в старых версиях.
- Контакт владельца рендерится через единый helper, который экранирует HTML и удаляет управляющие символы из env-значений.
- Для production используйте секреты/переменные окружения для токенов и `POSTGRES_PASSWORD`; не коммитьте реальные значения в `.env`.

---

## Деплой на VDS (Finland / 2 GB RAM)

Рекомендуемый режим — **long polling** (`python -m bot.main`), потому что APScheduler напоминания и weekly digest работают только в long-running процессе.

### Быстрый старт через Docker Compose

```bash
cp .env.example .env
# заполните BOT_TOKEN, GROUP_ID, OWNER_ID, ADMIN_IDS, POSTGRES_PASSWORD

docker compose up -d --build
docker compose logs -f bot
```

PostgreSQL слушает только внутреннюю docker-сеть. Бот не открывает входящие HTTP-порты.

Тюнинг PostgreSQL для 2 ГиБ RAM: `deploy/postgresql.vds.conf` (монтируется в контейнер). Параметры: `shared_buffers=128MB`, `max_connections=20` и др. — не повышайте `shared_buffers` до 256 МБ без нагрузочного теста.

Подробная пошаговая инструкция: **`deploy/VDS_SETUP.md`**.

### Резервное копирование

```bash
./deploy/backup_db.sh
```

Скрипт сохраняет `pg_dump` в `./backups/` и удаляет бэкапы старше 14 дней.

### systemd (опционально)

Пример unit-файла: `deploy/bot-adventure-time.service` (запускает `docker compose up -d` из `/opt/bot_adventure_time`).

Подробная инструкция: `deploy/VDS_SETUP.md`.

---

## Принципы внесения изменений

1. Не ломать обратную совместимость команд без явной миграции.
2. Все SQL-запросы — параметризованные.
3. Пользовательский ввод в HTML-сообщениях — экранировать.
4. Внешние HTTP-вызовы — с timeout и exception handling.
5. В пошаговых FSM-командах в ЛС промежуточные сообщения бота удаляются перед следующим шагом/итогом, а итоговые сообщения и обычные меню/карточки не помечаются на удаление.
6. Любое заметное изменение поведения — отражать в `README.md` и `промт.txt`.

---

## Частые точки диагностики

- Бот «не отвечает» в ЛС на шаге FSM:
  - проверить middleware/guard и активные состояния;
  - проверить, что промежуточные подсказки отправляются через `answer_private_intermediate`, а итоговые ответы — через `answer_private_final`.
- Событие не публикуется в группу:
  - проверить `GROUP_ID`, права бота в группе/теме, наличие forum topics.
- Нет данных в БД:
  - проверить `DATABASE_URL` / `PG*`, что PostgreSQL доступен из контейнера `bot`.
- Нет напоминаний:
  - проверить старт scheduler и восстановление jobs.
- На iPhone ссылка «открыть сообщение» в афише ведёт в группу, а не на карточку:
  - убедиться, что у события сохранены `message_id` и `thread_id` (тема форума);
  - ссылка должна быть вида `t.me/c/<chat>/<thread>/<message>`;
  - после обновления бота перепубликуйте афишу; старые сообщения со ссылками без `thread_id` на iOS могут вести себя некорректно.

---

## Чек-лист релиза

Перед релизом/PR обязательно проверить синхронизацию пользовательского поведения и документации:
- обновить `/help` (тексты в `common_feature/views.py`), если менялись команды, роли или доступность;
- обновить `README.md`;
- обновить `промт.txt`;
- добавить или актуализировать тесты в `tests/`;
- прогнать проверки и зафиксировать в PR «что/зачем/как проверено».

## Наблюдаемость и производительность

Что логируется из коробки:
- Метрики времени обработки update: `p50/p95/p99` (middleware `latency_metrics`).
- Метрики времени PostgreSQL-запросов: `p50/p95/p99` + warning для медленных запросов (`slow_pg_query_ms > 300`).
- Инициализированный размер пула PostgreSQL (`DB_POOL_MAX_SIZE`).

Как читать эти метрики:
- `p50` — типичная задержка.
- `p95` — задержка "на хвосте" для 5% самых медленных запросов.
- `p99` — почти worst-case, хороший индикатор деградации под нагрузкой.

Рекомендации под нагрузкой:
1. Прогнать стресс-тест при росте аудитории.
2. Снять `p50/p95/p99` по update и PostgreSQL-запросам.
3. Подобрать `DB_POOL_MAX_SIZE` по фактической latency (по умолчанию 5 для 2 ГиБ RAM).

## Troubleshooting

### Ошибка `cannot import name get_user_id_by_username from bot.database`
Причина: отсутствует функция в `bot/database_pg.py`, а `bot/database.py` реэкспортирует symbols через `from bot.database_pg import *`.

Проверка:
```bash
python - <<'PY'
from bot.database import get_user_id_by_username
print('ok', callable(get_user_id_by_username))
PY
```