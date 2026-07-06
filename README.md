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
4. Данные читаются/пишутся через `bot.database` → пакет `bot/db/` (слой совместимости: `bot/database_pg.py`).
5. Для событий и уведомлений ставятся задания в APScheduler (напоминания, подтверждение участия, digest, мониторинг).

### Хранение состояния
- FSM хранится в таблице `fsm_states` (PostgreSQL), чтобы сценарии не терялись при рестартах.
- Дневные лимиты команд — в таблице `user_command_usage_daily` (переживают рестарт процесса). Сутки считаются по `TIMEZONE` (по умолчанию `Europe/Moscow`). Callback-кнопки **внутри активных мастеров** (`/create_event`, `/split_bill`) лимит не тратят.

### Graceful shutdown
При остановке процесса (`docker compose stop`, SIGTERM) закрываются APScheduler и пул PostgreSQL (`dp.shutdown` в `bot/main.py`).
---

## Структура репозитория (подробно)

```text
.
├── docker-compose.yml
├── Dockerfile
├── deploy/
│   ├── deploy.sh
│   ├── backup_db.sh
│   ├── restore_db.sh
│   ├── verify_backup.sh
│   ├── backup-cron.example
│   ├── bot-adventure-time.service
│   ├── postgresql.vds.conf
│   ├── pg_hba.docker.conf
│   ├── server_hardening.example.sh
│   └── VDS_SETUP.md
├── backups/                         # pg_dump (не в git, кроме .gitkeep)
├── requirements.txt
├── промт.txt
├── README.md
├── tests/
│   ├── test_access_and_flows.py
│   ├── test_security_helpers.py
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
    ├── database.py                  # фасад: from bot.db import *
    ├── database_pg.py               # backward-compat re-export
    ├── healthcheck.py               # CLI для Docker healthcheck
    ├── db/                          # PostgreSQL-слой (модули по доменам)
    │   ├── schema.py                # init_db, индексы, миграции колонок
    │   ├── events.py
    │   ├── participants.py
    │   ├── attendance.py
    │   ├── members.py
    │   ├── split_bill.py
    │   ├── subscriptions.py
    │   ├── usage.py
    │   └── …
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
    └── utils/
        ├── __init__.py
        ├── design.py              # BRAND_VOICE, SEASON_COPY, визуальные primitives
        ├── scheduler.py
        ├── notifications.py         # ЛС с тихими часами
        ├── category_notify.py         # push по подпискам на категории
        ├── health.py                # heartbeat для healthcheck
        ├── monitoring.py              # периодические метрики + алерты owner
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
- `deploy/pg_hba.docker.conf` — правила аутентификации PG только для docker-сети.
- `deploy/VDS_SETUP.md` — пошаговая настройка VDS.
- `requirements.txt` — зависимости (`bot/requirements.txt`).
- `.env.example` — безопасный шаблон переменных окружения без секретов.
- `README.md` — этот документ.
- `промт.txt` — проектный технический промт/guide для разработки.

#### `bot/main.py`
- Инициализация бота, dispatcher, FSM storage.
- Регистрация роутеров и middleware.
- Режим polling.
- Ленивая инициализация БД/тем/планировщика/heartbeat/мониторинга.
- Graceful shutdown: планировщик + пул PG.
- Глобальный error-handler с уведомлением владельца в ЛС и троттлингом повторов ошибок.

#### `bot/config.py`
- Чтение env-переменных.
- Роли/лимиты/набор разрешённых команд.
- Таймзона, дайджест, напоминания, тихие часы, подтверждение участия, мониторинг.

#### `bot/db/` и `bot/database.py`
- `bot/database.py` и `bot/database_pg.py` — фасады; логика в пакете `bot/db/`.
- `schema.py` — создание таблиц, индексы, `DROP` legacy-таблиц.
- Доменные модули: события, участники, карпулинг, attendance, split bill, подписки, usage и т.д.

#### `bot/handlers/`
- `common_feature/handlers.py` — `/start`, `/help`, `/menu`, `/status`, `/donate`, onboarding, owner approve/reject, служебные команды.
- `common_feature/services.py` — проверка участия в группе, notify owner и т.д.
- `common_feature/views.py` — help, menu, onboarding-тексты (через `brand_voice` / `season_copy`).
- `events.py` + `event_scenarios/*` — FSM создания/редактирования/категоризации событий.
- `participation.py` — кнопки участия (в путь / резерв / в другой раз, карпулинг, «ищу попутку», подтверждение участия за 24ч).
- `my_events.py` — список событий + кнопка «📋 Копия #ID» (шаблон из прошлого мероприятия).
- `split_bill_feature/handlers.py` — FSM и callback-хендлеры split bill.
- `split_bill_feature/services.py` — формат карточки, шкала сбора, чек-лист оплат, напоминание должникам, автоподтягивание участников «going».
- `roadmap.py` — статистика, top, find, random optin/optout/pairs.
- `digest.py`, `subscriptions.py`, `my_events.py`, `admin.py` — профильные сценарии.

#### `bot/utils/design.py`
- Единый визуальный язык: `BRAND_VOICE`, `SEASON_COPY`, `WIZARD_PROMPTS`.
- Хелперы: `brand_voice()`, `season_copy()`, `category_accent_strip()`, `card_progress_bar()`, `money_collection_line()`.
- Сезонная шапка меню и дайджеста (зима / весна / лето / осень).

#### `bot/middleware/`
- `command_access.py` — role-based доступ и дневные лимиты **только в ЛС** (команды и callback); счётчик в `user_command_usage_daily`. В группе middleware не применяется — см. раздел «Безопасность».
- `topic_discoverer.py` — автообновление справочника тем по входящим апдейтам.
- `latency_metrics.py` — сбор времени обработки update (p50/p95/p99 через периодические логи).

#### `bot/filters/` и `bot/utils/command_policy.py`
- Фильтры прав (admin/registered/restricted command).
- `approved_member_callback_only` — декоратор для групповых inline-кнопок (участие, split bill).
- `can_view_command_hint()` — проверка доступа к подсказкам `menu_cmd_*` в `/menu`.

#### `bot/utils/`
- `scheduler.py` — напоминания, подтверждение участия за 24ч, digest, restore jobs.
- `notifications.py` — отправка ЛС с учётом тихих часов (`QUIET_HOURS_*`).
- `category_notify.py` — push подписчикам категории при публикации события.
- `monitoring.py` — периодический снимок метрик; алерт owner при высоком p95.
- `health.py` — heartbeat-файл для Docker healthcheck.
- `weather.py` — интеграция с погодой, HTTP session reuse, TTL-кеш и rate-limit.
- `metrics.py` — лёгкий in-memory сбор latency-метрик (p50/p95/p99).
- `event_links.py` — карты и календарные ссылки (Google/Яндекс).
- `helpers.py` — mention/username/ссылки на сообщения (`build_event_message_link` с поддержкой `thread_id` для Topics).
- `callbacks.py` — `finalize_callback`, безопасный парсинг `parse_callback_suffix_int` / `parse_callback_split_int`.
- `pairing.py` — алгоритм random-пар 1:1.

#### `tests/`
- Unit-тесты: тексты и брендинг, HTML-экранирование, доступы, FSM storage PG, pool, callbacks, scheduler.

---

## Команды бота

> Реестр команд: `bot/commands.py`. Доступность зависит от роли (`OWNER_ID`, `ADMIN_IDS`, запись в `approved_members`) и лимитов из `config.py`.

### Модель доступа

| Роль | Как получить | Что доступно |
|------|----------------|--------------|
| **Owner** | `OWNER_ID` в `.env` | Всё, без дневного лимита |
| **Admin** | `ADMIN_IDS` | Расширенные команды, с лимитом `ADMIN_DAILY_COMMAND_LIMIT` |
| **Approved member** | Владелец одобрил заявку (`approve_user_*`) или запись уже есть в `approved_members` | Пользовательские команды из `MEMBER_ALLOWED_COMMANDS` |
| **Outsider** | Не одобрен ботом | По умолчанию только `/start` и `/donate` |

**Важно:** нахождение в Telegram-группе **не равно** одобрению ботом. Участник, добавленный в группу в обход бота (инвайт админа Telegram, прямая ссылка), не получает команды участника, пока владелец не одобрит его через бота или не появится запись в `approved_members` (например, после `approve_user_*` или `/sync_members` для уже одобренных).

Онбординг: `/start` → правила → заявка владельцу → `approve_user_*` → одноразовая invite-ссылка → участник в группе и в `approved_members`.

### Базовые
- `/start` — вход/онбординг; для одобренного участника — приветствие и кнопка перехода в `/menu`.
- `/help` — подробная справка без прикреплённого меню.
- `/menu` — Control Center с разделами 🎉 События, 🧾 Деньги, 🔔 Уведомления, 🤝 Комьюнити (+ админ для админов).
- `/status` — быстрая проверка, что бот онлайн.
- `/donate` — ссылки на сборы (Сбербанк / Т-Банк) в ЛС; доступна и не-участникам (`OUTSIDER_ALLOWED_COMMANDS=start,donate`).

### Мероприятия
- `/create_event` — пошаговое создание события (в т.ч. шаг «ответственный», выбор формата цены, превью перед публикацией).
- `/my_events` — ваши события; кнопка «📋 Копия #ID» — шаблон из прошлого мероприятия.
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
- При создании участники «going» из связанного мероприятия подтягиваются автоматически.
- Кнопка «🔔 Напомнить должникам» — только в ЛС организатора после создания чека.
- `/split_bill_add <id> <user_id|@username>` / `/split_bill_remove <id> <user_id|@username>` — ручное управление участниками.

### Сервисные/админские
- `/roles`, `/usage_stats`, `/debug_info`, `/list_topics`, `/update_topic_names`, `/admin_report`, `/pending_intro`, `/send_events_list`, `/member_reengage`, `/sync_members`, `/reset_user_limit <user_id|@username>`.

### UX и визуальное оформление
- Тон голоса бота — приключенческий (Adventure Time community), без копирования персонажей мультсериала. Тексты централизованы в `bot/utils/design.py` (`BRAND_VOICE`, `SEASON_COPY`, `WIZARD_PROMPTS`).
- `/menu` — сезонная шапка (❄️/🌸/☀️/🍂), слоган «Куда отправимся сегодня?». Раздел **События** → 👀 Смотреть / ➕ Создать / 🛠 Управление. Кнопки меню — человекочитаемые названия (без `/команд` в подписях).
- Кнопки участия в **групповой** карточке: `✅ В путь!` / `⏳ В резерве` / `❌ В другой раз`; в **ЛС** (через «Мои встречи») — персонализированные (`❌ Снять запись`, `❌ Снять резерв`).
- Удаление мероприятия — только в ЛС организатора, с подтверждением; на публичной карточке кнопки «🗑 Удалить» нет.
- За 24 ч до события (настраивается `ATTENDANCE_CONFIRM_HOURS`) участникам «going» приходит ЛС с подтверждением «всё ещё иду».
- При публикации события подписчики категории получают push в ЛС (с учётом тихих часов `QUIET_HOURS_*`).
- Карточка мероприятия: заголовок → статус → шкала мест `🎟 ████░░░░ 4/10`; компактные ссылки; без текстового CTA внизу; `🆔 ID` только в ЛС организатора.
- Дайджест: «Афиша приключений» + подсказка для iPhone в конце; пустой период — «Тишина в Ланде Ооо…».
- Split-bill: шкала сбора; закрытие чека — с подтверждением; «🔔 Напомнить должникам» — в ЛС организатора.
- Онбординг: краткие правила + «📜 Полные правила»; после `/start` — чеклист «что дальше»; кнопка `🚀 Старт`.
- Мастер событий: быстрые кнопки даты («Сегодня вечером», «Завтра», «В субботу»); превью с `🗺️ Публикуем!`.
- Подписки: автосохранение при каждом выборе. «Мои встречи»: кнопки `📅 05.07 · Название`.
- Статусы карточки: 🔥 скоро, ✅ набор открыт, ⏳ резерв, 🚫 мест нет.

### Важные детали поведения
- `/pending_intro` — единая команда контроля «Рассказа о себе»: показывает pending-участников (с кнопками отметки) и сводный статус по всем актуальным участникам группы.
- Кнопки `menu_cmd_*` в `/menu` показывают **подсказку** по команде (синтаксис и описание), но не выполняют её; админские подсказки скрыты от обычных участников (`can_view_command_hint`).
- Групповые inline-кнопки (участие, split bill) проверяют `is_member_approved` через `@approved_member_callback_only`; отказ от участия (`decline_*`) продвигает резерв только если пользователь реально был в списке.
- Split-bill карточки в группе: все пользовательские поля (название, реквизиты, ФИО) экранируются для `parse_mode=HTML`.
- В командах, где оператор задаёт участника вручную (`/set_responsible`, `/add_participant_manual`, `/split_bill_add`, `/split_bill_remove`, `/reset_user_limit` и шаг «ответственный» в мастере), можно указать **числовой `user_id` или `@username`**. Поиск: БД → fallback по одобренным участникам через Telegram API. Для команд управления мероприятием действует проверка «только актуальные участники группы».
- Для random 1:1 в пулы и пары попадают только пользователи из `approved_members` (исключённые участники автоматически не участвуют). `/random_pairs` публикует общую карточку в выбранную группу/подгруппу и не рассылает личные уведомления о парах.
- `/send_event_card` публикует короткое сообщение со ссылкой на основную карточку мероприятия, а не вторую интерактивную карточку; callback-кнопки продолжают обновлять только основную карточку.
- `/digest` и `/my_digest` используют ссылки на основные карточки мероприятий, если у события сохранён `message_id`.
- В афише, дайджестах и `/send_events_list` учитываются мероприятия с **периодом действия** (`period_end`): если период ещё не закончился, событие попадает в список даже при старте в прошлом.
- Ссылки на карточки в форумных темах строятся как `t.me/c/<chat>/<thread>/<message>` (нужен `thread_id`); без него iOS-клиент Telegram часто открывает только группу.
- В split-bill сценарии (`/split_bill`) промежуточные сообщения в ЛС удаляются, чтобы не засорять диалог; обычные меню/карточки не удаляются без явной wizard-политики.
- Владелец получает технические алерты о необработанных ошибках бота в ЛС (с защитой от спама повторяющимися ошибками).

> `/send_events_list` и автоматическая еженедельная афиша используют **один формат** (quote-блоки со ссылками). Тема автоматической афиши — `DIGEST_THREAD_ID` в `.env` (узнать ID: `/list_topics`). В конце афиши — подсказка для iPhone (переслать в «Избранное», если ссылка не срабатывает).

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
- `DIGEST_DAY_OF_WEEK`, `DIGEST_HOUR`, `DIGEST_THREAD_ID` — расписание и тема еженедельной афиши (`thread_id` из `/list_topics`)
- `MEMBER_DAILY_COMMAND_LIMIT` — лимит команд/callback в ЛС для участника (по умолчанию **40**; мастера не считаются)
- `QUIET_HOURS_START`, `QUIET_HOURS_END` — тихие часы для ЛС-уведомлений (по умолчанию 23:00–08:00, `TIMEZONE`)
- `ATTENDANCE_CONFIRM_HOURS` — за сколько часов до события спрашивать подтверждение участия (по умолчанию 24)
- `MONITORING_P95_ALERT_MS`, `MONITORING_INTERVAL_MINUTES` — периодический снимок метрик и алерт owner при высоком p95
- `BOT_HEARTBEAT_PATH`, `BOT_HEARTBEAT_INTERVAL_SECONDS` — heartbeat для Docker healthcheck (`python -m bot.healthcheck`)
- `BACKUP_RETENTION_DAYS` — срок хранения `pg_dump` в `./backups/` (по умолчанию 14)
- Лимиты и списки команд — см. `config.py`

### Производительность и безопасность
- `aiohttp>=3.13.4` — закрыты известные DoS/header parser уязвимости
- Погодный клиент: TTL-кеш 300 с, rate-limit 2 с на ключ (задано в `bot/utils/weather.py`)
- PostgreSQL на VDS: `deploy/postgresql.vds.conf` + `deploy/pg_hba.docker.conf` (только private-сети Docker); **не публикуйте** `5432` на хост (`expose`, не `ports`)
- Бэкапы БД: `chmod 600` на `.sql.gz` и `.sha256`; каталог `backups/` в `.gitignore`

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

### Секреты и инфраструктура
- Не храните ключи/токены в репозитории; используйте `.env` (в `.gitignore`) и секреты CI/CD.
- Для PostgreSQL — параметризованные запросы через asyncpg pool (`bot/db_pool.py`).
- Docker: бот под non-root (`botuser`); PostgreSQL доступен только внутри docker-сети.
- **Никогда** не добавляйте в `docker-compose.yml` строку `ports: "5432:5432"` для postgres.

### Доступ и авторизация
- ЛС: роли и дневные лимиты — `middleware/command_access.py` + `config.py` + `bot/commands.py`.
- Группа: middleware **не** проверяет роли; каждый callback-хендлер обязан сам проверять права (`@approved_member_callback_only`, `_can_manage_event`, `_can_view_event` и т.д.).
- Одобрение участника — только через владельца (`approve_user_*`); автоматическое добавление в `approved_members` при вступлении в Telegram-группу **отключено**.
- Админ-команды: `@admin_only`, `@restricted_command`, проверка в `menu_cmd_*` через `can_view_command_hint`.

### Ввод пользователя и HTML
- Карточки событий (`texts.py`), split bill (`split_bill_feature/services.py`), админ-ответы (`debug_info`, `list_topics`, `admin_report`) — `html.escape()` для пользовательских данных.
- Контакт владельца — `build_owner_contact_html()` (валидация username/URL, strip control chars).
- Callback `data` — парсить через `parse_callback_suffix_int` / `parse_callback_split_int`, не `int(callback.data.split(...))` без проверки.

### Резервные копии
- Дамп содержит PII и реквизиты split bill — храните `backups/` с правами `600`, вне web-root, с ротацией `BACKUP_RETENTION_DAYS`.
- Восстановление — только осознанно через `restore_db.sh`.

### Синхронизация при изменениях
При изменении команд/доступов обновляйте:
1. `/help` и `common_feature/views.py`
2. `README.md` и `промт.txt`
3. тесты в `tests/test_access_and_flows.py`, `tests/test_security_helpers.py`

---

## Что обновилось в последних изменениях

- **Безопасность (2026-07):** разделение «в группе Telegram» vs «одобрен ботом»; HTML-escape в split bill и админ-ответах; защита `decline_*` от манипуляции резервом; IDOR-fix в `myevent_{id}`; `pg_hba.docker.conf`; `chmod 600` на бэкапы; `can_view_command_hint` для `menu_cmd_*`; безопасный парсинг callback.
- **Слой БД:** монолитный `database_pg.py` разбит на пакет `bot/db/`; фасады `bot/database.py` и `bot/database_pg.py` сохранены для совместимости.
- **Лимиты в PostgreSQL:** дневные лимиты команд/callback в ЛС (`user_command_usage_daily`), сутки по `TIMEZONE`; callback внутри мастеров не тратят лимит; дефолт участника 40/сутки; `/reset_user_limit`.
- **Мастер событий:** шаг «ответственный»; единый формат афиши (ручная + авто); `DIGEST_THREAD_ID`.
- **Участие:** подтверждение «всё ещё иду» за 24 ч; статус «🚗 Ищу попутку»; копия прошлого события из `/my_events`.
- **Уведомления:** тихие часы для ЛС; push подписчикам категории при публикации события.
- **Split bill:** автоподтягивание участников «going»; кнопка «🔔 Напомнить должникам».
- **Эксплуатация:** graceful shutdown (scheduler + pool); Docker healthcheck бота; heartbeat + мониторинг p95 с алертом owner.
- **Бэкапы:** `backup_db.sh` с `--clean --if-exists`, sha256, лог; скрипты `restore_db.sh` и `verify_backup.sh`; пример cron `backup-cron.example`.
- **Индексы** на `participants`, `events`, `fsm_states`, `user_category_subscriptions`; удалена legacy-таблица `reminder_jobs`.
- Прежние изменения: афиша с `period_end` и `thread_id` для iOS; VDS Docker Compose; брендинг в `design.py`; `/donate`; split-bill шкала сбора; документация `deploy/VDS_SETUP.md`.

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

- Минимальная версия `aiohttp` — `3.13.4`: закрывает известные проблемы multipart DoS, zip bomb и небезопасных response headers.
- Контакт владельца — `build_owner_contact_html()` (escape HTML, strip control chars, валидация `@username` и HTTPS).
- Production: секреты только в env; `POSTGRES_PASSWORD` без `$` (иначе ломается docker-compose).
- PostgreSQL: `pg_hba.docker.conf` ограничивает клиентов private-сетями; порт 5432 не публикуется на хост.
- Бэкапы: права `600`, каталог не в git; дамп содержит чувствительные данные.
- Участники бота одобряются владельцем; членство в Telegram-группе само по себе доступ к командам не даёт.

Подробнее — раздел **«Безопасность и эксплуатационные практики»** выше.

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

PostgreSQL слушает интерфейсы внутри docker-сети (`listen_addresses='*'` в контейнере — нормально). Снаружи порт **не** проброшен. Дополнительно: `deploy/pg_hba.docker.conf` разрешает подключения только с private-подсетей (10/8, 172.16/12, 192.168/16, localhost).

**Не добавляйте** `ports: "5432:5432"` у сервиса `postgres` — это откроет БД на хост.

**Healthcheck:** у `postgres` — `pg_isready`; у `bot` — `python -m bot.healthcheck` (проверка свежести heartbeat-файла). Статус: `docker compose ps`.

Тюнинг PostgreSQL для 2 ГиБ RAM: `deploy/postgresql.vds.conf` (монтируется в контейнер). Параметры: `shared_buffers=128MB`, `max_connections=20` и др. — не повышайте `shared_buffers` до 256 МБ без нагрузочного теста.

Подробная пошаговая инструкция: **`deploy/VDS_SETUP.md`**.

### Резервное копирование

```bash
./deploy/backup_db.sh
```

Скрипт сохраняет `pg_dump --clean --if-exists` в `./backups/`, пишет sha256 и лог; выставляет **`chmod 600`** на архив и checksum; удаляет файлы старше `BACKUP_RETENTION_DAYS` (по умолчанию 14). Пример cron: `deploy/backup-cron.example`.

> Дамп содержит персональные данные и реквизиты split bill. Храните `backups/` только на сервере с ограниченным доступом.

Проверка целостности и восстановление:

```bash
./deploy/verify_backup.sh backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz
./deploy/restore_db.sh backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz
```

`restore_db.sh` останавливает бота, восстанавливает БД и поднимает сервисы снова — используйте только при осознанном откате данных.

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
- Нет напоминаний / нет подтверждения участия:
  - проверить старт scheduler и восстановление jobs;
  - `ATTENDANCE_CONFIRM_HOURS` и что до события осталось меньше этого окна.
- Контейнер `bot` в статусе `unhealthy`:
  - `docker compose logs bot`; проверить heartbeat (`BOT_HEARTBEAT_PATH`) и что процесс не завис.
- Участник в группе, но бот отвечает «доступ не подтверждён»:
  - он не в `approved_members`; владелец должен одобрить заявку (`approve_user_*`) или участник проходит онбординг через `/start`.
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
- Периодический снимок метрик (`bot/utils/monitoring.py`); при p95 выше `MONITORING_P95_ALERT_MS` — алерт владельцу в ЛС.
- Docker healthcheck бота: heartbeat-файл (`BOT_HEARTBEAT_PATH`), проверка `python -m bot.healthcheck`.

Как читать эти метрики:
- `p50` — типичная задержка.
- `p95` — задержка "на хвосте" для 5% самых медленных запросов.
- `p99` — почти worst-case, хороший индикатор деградации под нагрузкой.

Рекомендации под нагрузкой:
1. Прогнать стресс-тест при росте аудитории.
2. Снять `p50/p95/p99` по update и PostgreSQL-запросам.
3. Подобрать `DB_POOL_MAX_SIZE` по фактической latency (по умолчанию 5 для 2 ГиБ RAM).

## Troubleshooting

### Ошибка `cannot import name … from bot.database`
Причина: символ не экспортирован из `bot/db/__init__.py` или устаревший импорт из `bot.database_pg`.

Проверка:
```bash
python - <<'PY'
from bot.database import get_user_id_by_username
print('ok', callable(get_user_id_by_username))
PY
```