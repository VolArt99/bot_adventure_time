# Настройка VDS для Bot Adventure Time

Пошаговая инструкция **строго по порядку**: идите от §1 к §10, не перескакивая. Справочные разделы (мониторинг, проблемы) — после первого запуска.

**Профиль сервера (serv.host, Финляндия):**

| Параметр | Значение |
|----------|----------|
| CPU | 1 vCPU (AMD EPYC-7502) |
| RAM | 2 ГиБ |
| Диск | 25 ГиБ NVMe |
| Сеть | 250 Мбит/с (burst до 1 Гбит/с) |
| IPv4 | 1 адрес |
| IPv6 | подсеть /64 |
| Защита | Anti-DDoS (базовая) |
| Виртуализация | KVM |

Бот работает в **polling-режиме** (исходящие запросы к Telegram API). Входящие HTTP-порты **не нужны** — firewall можно держать закрытым, кроме SSH.

> SSH-подробности со скриншотами: [«Купили сервер. Что дальше?»](https://serv.host/articles/23/)

---

## Содержание

**Первый запуск (по порядку):**

1. [Первый вход и безопасность SSH](#1-первый-вход-и-безопасность-ssh)
2. [Подготовка сервера](#2-подготовка-сервера)
3. [Установка Docker и Git](#3-установка-docker-и-git)
4. [Telegram — до первого запуска бота](#4-telegram--до-первого-запуска-бота)
5. [Развёртывание бота на сервере](#5-развёртывание-бота-на-сервере)
6. [Telegram — проверка после запуска](#6-telegram--проверка-после-запуска)
7. [Автозапуск и бэкапы](#7-автозапуск-и-бэкапы)

**Эксплуатация:**

8. [Обновление бота](#8-обновление-бота)
9. [Мониторинг и диагностика](#9-мониторинг-и-диагностика)
10. [Типичные проблемы](#10-типичные-проблемы)

**Итог:** [Чеклист первого запуска](#чеклист-первого-запуска)

**Справка:** [Приложение A — переустановка ОС](#приложение-a--переустановка-ос-на-servhost) · [Приложение B — ресурсы и PostgreSQL](#приложение-b--ресурсы-и-postgresql)

---

## 1. Первый вход и безопасность SSH

### 1.1. Данные от serv.host

После заказа VDS на почту приходит письмо с:

- **IPv4-адрес** сервера
- **логин** (обычно `root`)
- **пароль** root

Сохраните письмо в менеджере паролей, но **не оставляйте пароль из письма как единственный способ входа** — ниже настроим ключи.

> Нужна другая версия Ubuntu? Сначала [Приложение A](#приложение-a--переустановка-ос-на-servhost), затем возвращайтесь сюда.

### 1.2. Подключение с Windows

Рекомендуемый клиент — [MobaXterm Home Edition](https://mobaxterm.mobatek.net/download-home-edition.html) (есть встроенный SFTP).

1. **Session → SSH**
2. **Remote host** — IPv4 из письма
3. **Username** — `root`
4. **Port** — `22` (если не меняли — см. §2.4)
5. При первом подключении нажмите **Accept** (сохранение fingerprint сервера)
6. Вставьте пароль из письма (символы при вводе не отображаются)

Альтернатива — PowerShell / Windows Terminal:

```powershell
ssh root@ВАШ_IPv4
```

### 1.3. Смена пароля root

```bash
passwd
```

### 1.4. SSH-ключ вместо пароля (рекомендуется)

**На Windows (MobaXterm):** Tools → MobaKeyGen (SSH key generator)

1. Тип ключа: **EdDSA / Ed25519**
2. **Generate** → сохраните закрытый ключ (**Save private key**)
3. Скопируйте **открытый ключ** (поле Public key)

**На сервере** (пока ещё вошли по паролю):

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAA...ваш_ключ... комментарий' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Проверьте вход по ключу в **новой** сессии, не закрывая текущую.

### 1.5. Отключение входа по паролю (cloud-init)

На образах serv.host (Ubuntu) настройки SSH часто переопределяются **не** в `/etc/ssh/sshd_config`, а в:

```
/etc/ssh/sshd_config.d/50-cloud-init.conf
```

После проверки входа по ключу:

```bash
nano /etc/ssh/sshd_config.d/50-cloud-init.conf
```

Замените `PasswordAuthentication yes` на `PasswordAuthentication no`.

Перезапуск SSH:

```bash
# Ubuntu 22.04
sudo systemctl restart ssh

# Ubuntu 24.04 — обязательно так:
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
```

### 1.6. Отдельный пользователь для деплоя

Не работайте постоянно под `root`:

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

**Дальше все шаги §2–§8 выполняйте под `deploy`** (переподключитесь по SSH). Команды с `sudo` — где указано.

---

## 2. Подготовка сервера

### 2.1. Обновление системы, Git и часовой пояс

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git
sudo timedatectl set-timezone Europe/Helsinki
timedatectl
```

> **Часовой пояс сервера** — Helsinki (логи, cron). **Часовой пояс бота** — `TIMEZONE=Europe/Moscow` в `.env` (§5.2); это разные настройки.

### 2.2. Firewall и fail2ban

```bash
sudo apt install -y ufw fail2ban unattended-upgrades

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw --force enable

sudo dpkg-reconfigure -plow unattended-upgrades
```

- **ufw** — только SSH снаружи; 80/443 для бота **не нужны**
- **fail2ban** — защита от перебора SSH
- **unattended-upgrades** — security-патчи

### 2.3. Swap (рекомендуется для 2 ГиБ RAM)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### 2.4. Смена SSH-порта (опционально)

Пропустите, если оставляете порт **22**.

1. В `/etc/ssh/sshd_config.d/50-cloud-init.conf` добавьте строку, например: `Port 1337`
2. **До перезапуска SSH** откройте порт в firewall:

```bash
sudo ufw allow 1337/tcp
```

3. Перезапустите SSH (команды — в §1.5)
4. Обновите порт в MobaXterm / SSH-клиенте
5. Проверьте вход в **новой** сессии, старую не закрывайте

---

## 3. Установка Docker и Git

Git уже установлен в §2.1. Устанавливаем Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

Проверка:

```bash
docker --version
docker compose version
```

---

## 4. Telegram — до первого запуска бота

> Выполняется **на вашем компьютере / телефоне**, параллельно с §1–§3 или сразу после них. К §5 нужны **токен** и **GROUP_ID**.

### 4.1. Создание бота

1. @BotFather → `/newbot`
2. Сохраните **токен** — понадобится для `BOT_TOKEN` в §5.2

### 4.2. Группа и ID

1. Создайте **супергруппу с темами (форум)**
2. Добавьте бота **администратором** (права: удаление, закрепление, управление темами)
3. Узнайте **GROUP_ID** через @getidsbot (добавьте в группу) или @userinfobot — число вида `-1001234567890`

### 4.3. Privacy mode

@BotFather → Bot Settings → **Group Privacy** → **Turn off** — иначе бот не увидит сообщения в темах.

### 4.4. Команды в BotFather (можно сейчас или после §6)

@BotFather → `/setcommands`:

```
start - Запуск и онбординг
help - Справка
menu - Главное меню
donate - Поддержать бота
status - Проверить работу бота
create_event - Создать мероприятие
my_events - Мои мероприятия
edit_event - Редактировать мероприятие
digest - Афиша
subscriptions - Подписки
split_bill - Разделить чек
```

> Полный список пользовательских команд бот публикует сам при старте (`bot/main.py` → `setup_bot_commands`). Справка `/help` и разделы `/menu` синхронизированы с `bot/commands.py`.

Запишите для §5.2: **BOT_TOKEN**, **GROUP_ID**, ваш **OWNER_ID**, **ADMIN_IDS**.

---

## 5. Развёртывание бота на сервере

> Предусловия: §1–§3 выполнены, из §4 есть токен и GROUP_ID.

### 5.1. Клонирование репозитория

```bash
sudo mkdir -p /opt/bot_adventure_time
sudo chown $USER:$USER /opt/bot_adventure_time
git clone https://github.com/ВАШ_АККАУНТ/bot_adventure_time.git /opt/bot_adventure_time
cd /opt/bot_adventure_time
```

### 5.2. Создание `.env`

```bash
cp .env.example .env
nano .env
```

**Обязательно заполните:**

| Переменная | Откуда взять |
|------------|--------------|
| `BOT_TOKEN` | §4.1 |
| `GROUP_ID` | §4.2 |
| `OWNER_ID` | ваш Telegram user ID |
| `ADMIN_IDS` | ID админов через запятую |
| `POSTGRES_PASSWORD` | придумайте надёжный пароль (без символа `$` — см. §10) |
| `ENV` | `production` |
| `TIMEZONE` | `Europe/Moscow` |

**Рекомендуется:**

| Переменная | Значение |
|------------|----------|
| `AUTO_INIT_DB` | `1` |
| `DB_POOL_MAX_SIZE` | `5` |
| `DONATION_SBERBANK_URL` / `DONATION_TBANK_URL` | ссылки для `/donate` |
| `WEATHER_API_KEY` | OpenWeatherMap (опционально) |
| `MEMBER_DAILY_COMMAND_LIMIT` | `40` — лимит команд в ЛС для участника |
| `DIGEST_THREAD_ID` | `message_thread_id` темы для еженедельной афиши (§4.2, `/list_topics`) |

> `DATABASE_URL` и `PGHOST`/`PGPASSWORD` для Docker **не нужны** — бот подключается к `postgres` через `env_file` и переменные в `docker-compose.yml`.

**Пример минимального `.env` (строки без `#`):**

```env
BOT_TOKEN=...
GROUP_ID=-100...
OWNER_ID=...
ADMIN_IDS=...
POSTGRES_USER=bot
POSTGRES_DB=adventure_time
POSTGRES_PASSWORD=ваш_надёжный_пароль
ENV=production
TIMEZONE=Europe/Moscow
AUTO_INIT_DB=1
```

### 5.3. Первый запуск

```bash
bash deploy/deploy.sh
```

Или вручную:

```bash
docker compose build bot
docker compose up -d
```

### 5.4. Проверка логов

```bash
docker compose logs -f bot
docker compose ps
```

Успех: в логах **Start polling**, оба контейнера **Up**, postgres **healthy**.

Если ошибка про `GROUP_ID` или `BOT_TOKEN` — вернитесь к §5.2, исправьте `.env`, затем:

```bash
docker compose up -d
```

---

## 6. Telegram — проверка после запуска

> Бот уже запущен (§5). Проверьте в Telegram:

| Действие | Ожидаемый результат |
|----------|---------------------|
| `/status` в ЛС | «Компаньон на связи» |
| `/menu` (одобренный участник) | «Центр приключений», разделы События / Скинуться / Уведомления / Комьюнити; в Управлении — ⌨️ подсказки команд |
| `/start` (одобренный участник) | чеклист + кнопки **📣 Афиша** и **🏠 Открыть меню** |
| `/menu` → Уведомления → Режим | переключение `all` / `mine` / `off`, сохраняется в БД |
| `/help` | все команды участника (+ админ-блок для админов) |
| `/debug_info` (админ) | корректный GROUP_ID |
| `/menu` → `menu_cmd_debug_info` (участник) | «Недостаточно прав» — админ-подсказки скрыты |
| Сообщение в теме форума | тема в `/list_topics` |
| Участник в группе без `approve_user_*` | `/start` → «бот ещё не подтвердил доступ» |

Если `/debug_info` показывает неверный GROUP_ID — исправьте `.env` (§5.2) и `docker compose restart bot`.

---

## 7. Автозапуск и бэкапы

> Выполняется из каталога проекта:

```bash
cd /opt/bot_adventure_time
```

### 7.1. Systemd (после перезагрузки сервера)

```bash
sudo cp deploy/bot-adventure-time.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bot-adventure-time
sudo systemctl start bot-adventure-time
sudo systemctl status bot-adventure-time
```

Unit запускает `docker compose up -d` из `/opt/bot_adventure_time`. При другом пути — поправьте `WorkingDirectory` в unit-файле.

### 7.2. Ежедневный бэкап БД

```bash
mkdir -p /opt/bot_adventure_time/backups
crontab -e
```

Строка (03:00 по времени **сервера** — Helsinki) — готовый пример в `deploy/backup-cron.example`:

```
0 3 * * * /opt/bot_adventure_time/deploy/backup_db.sh >> /opt/bot_adventure_time/backups/backup.log 2>&1
```

Ручной бэкап:

```bash
cd /opt/bot_adventure_time
bash deploy/backup_db.sh
ls -lh backups/
```

Скрипт пишет `pg_dump --clean --if-exists`, sha256 (`.sha256`), лог в `backups/backup.log`, выставляет **`chmod 600`** на архив и checksum, удаляет файлы старше `BACKUP_RETENTION_DAYS` (по умолчанию 14).

> Дамп содержит персональные данные участников и реквизиты split bill. Каталог `backups/` не должен быть доступен извне; проверьте `ls -l backups/` — права `-rw-------`.

Проверка целостности:

```bash
bash deploy/verify_backup.sh backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz
```

### 7.3. Восстановление из бэкапа (если понадобится)

**Предупреждение:** восстановление перезапишет текущую БД. Остановите бота и используйте скрипт:

```bash
cd /opt/bot_adventure_time
bash deploy/restore_db.sh backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz
```

Скрипт останавливает контейнер `bot`, восстанавливает PostgreSQL и поднимает сервисы снова.

---

## 8. Обновление бота

```bash
cd /opt/bot_adventure_time
git pull
bash deploy/deploy.sh
docker compose logs --tail=50 bot
```

---

## 9. Мониторинг и диагностика

> Справочный раздел; на первом запуске достаточно §5.4 и §6.

```bash
cd /opt/bot_adventure_time

docker compose ps               # health: postgres (pg_isready) + bot (heartbeat)
docker compose logs -f bot      # логи бота
docker compose logs -f postgres # логи БД
docker stats                    # RAM/CPU контейнеров
htop                            # ресурсы сервера
df -h                           # диск
free -h                         # swap
```

В логах бота: `slow_pg_query_ms` (>300 мс), `update_processing` / `pg_query` (p50/p95/p99).

Периодически (`MONITORING_INTERVAL_MINUTES`, по умолчанию 60) бот логирует снимок метрик; при p95 выше `MONITORING_P95_ALERT_MS` (по умолчанию 2000 мс) владелец получает алерт в ЛС.

Если `docker compose ps` показывает `bot` как `unhealthy` — проверьте heartbeat (`BOT_HEARTBEAT_PATH`, по умолчанию `/tmp/bot_heartbeat`) и логи процесса.

Перезапуск:

```bash
docker compose restart bot
# или полный:
docker compose down && docker compose up -d
```

Команды в Telegram: `/status`, `/menu`, `/donate`, `/debug_info`, `/usage_stats` — см. `README.md`.

---

## 10. Типичные проблемы

### `Conflict: can't use getUpdates while webhook is active`

**Причина:** у бота на серверах Telegram всё ещё включён **webhook** (старый деплой, тест, другой сервер).

**Быстро снять webhook** (подставьте токен из `.env`):

```bash
curl -s "https://api.telegram.org/botВАШ_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
```

Ответ: `{"ok":true,...}`.

Или из контейнера:

```bash
docker compose run --rm bot python -c "
import asyncio, os
from aiogram import Bot
async def main():
    b = Bot(os.environ['BOT_TOKEN'])
    await b.delete_webhook(drop_pending_updates=True)
    await b.session.close()
    print('webhook deleted')
asyncio.run(main())
"
```

Затем: `docker compose restart bot`.

В новых версиях кода webhook снимается автоматически при старте (`bot/main.py`).

### Бот не отвечает

1. `docker compose ps` — `bot` в статусе `Up`?
2. `docker compose logs bot` — ошибки токена, GROUP_ID, БД?
3. `BOT_TOKEN` в `.env` (§5.2)

### Ошибка PostgreSQL

1. `postgres` healthy?
2. `POSTGRES_PASSWORD` в `.env`
3. Подождите 10–15 сек после `up -d`

### GROUP_ID обязателен

При `ENV=production` без `GROUP_ID` бот не стартует (§4.2, §5.2).

### OOM (нехватка RAM)

1. `docker stats`, `free -h`
2. Swap включён? (§2.3)
3. Лимиты в `docker-compose.yml` — см. [Приложение B](#приложение-b--ресурсы-и-postgresql)

### Бот не видит темы

1. Privacy mode выключен (§4.3)
2. Сообщение в теме форума
3. `/list_topics`

### SSH: пароль не отключается

Файл `/etc/ssh/sshd_config.d/50-cloud-init.conf` — [статья serv.host](https://serv.host/articles/23/).

### SSH-порт на Ubuntu 24.04

```bash
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
```

### `/donate` без кнопок

Задайте `DONATION_SBERBANK_URL` и `DONATION_TBANK_URL` в `.env`.

### На iPhone ссылка из афиши открывает группу, а не карточку

**Симптом:** в сообщении «Актуальная афиша…» тап по «открыть сообщение» на iOS ведёт в чат группы; на Android или после пересылки в «Избранное» — на нужную карточку.

**Причина:** мероприятие опубликовано в **теме форума** (Topics). Для deep-link нужен формат `https://t.me/c/<chat_id>/<thread_id>/<message_id>`. Старые ссылки без `thread_id` iOS обрабатывает ненадёжно.

**Что сделать:**
1. Обновить бота до версии, где `build_event_message_link` передаёт `thread_id`.
2. Убедиться, что у события в БД есть `message_id` и `thread_id` (создаются при публикации карточки).
3. Переопубликовать афишу командой `/send_events_list` — старые сообщения со «короткими» ссылками не исправятся сами.

**Проверка ссылки:** в Telegram Desktop — ПКМ по карточке мероприятия → «Копировать ссылку на сообщение»; сравните с тем, что генерирует бот.

### Бот не подключается к PostgreSQL (`name resolution` / `Temporary failure`)

**Причина:** в `.env` раскомментирован **`DATABASE_URL`** или **`PGHOST=localhost`** — бот ищет БД не на сервисе `postgres` в Docker.

**Решение:**

1. В `.env` **закомментируйте или удалите** строки:
   ```env
   # DATABASE_URL=...
   # PGHOST=localhost
   # PGUSER=...
   # PGPASSWORD=...
   # PGDATABASE=...
   ```
2. Оставьте только:
   ```env
   POSTGRES_USER=bot
   POSTGRES_DB=adventure_time
   POSTGRES_PASSWORD=ваш_пароль_без_символа_$
   ```
3. Перезапуск:
   ```bash
   cd /opt/bot_adventure_time
   git pull
   docker compose down
   docker compose up -d --build
   ```
4. Проверка:
   ```bash
   docker compose ps
   docker compose exec bot printenv PGHOST DATABASE_URL POSTGRES_USER
   ```
   Ожидается: `PGHOST=postgres`, `DATABASE_URL` пустой или отсутствует.

### `Connection refused` к PostgreSQL (`172.x.x.x`, 5432)

**Причина:** в `deploy/postgresql.vds.conf` не было `listen_addresses = '*'`, или после обновления не подключён `pg_hba.docker.conf`.

**Решение:**

```bash
cd /opt/bot_adventure_time
git pull   # postgresql.vds.conf + pg_hba.docker.conf + hba_file в docker-compose.yml
docker compose down
docker compose up -d --build
docker compose logs --tail=20 postgres
```

Проверка из контейнера бота:

```bash
docker compose run --rm bot python -c "
import asyncio, os, asyncpg
async def main():
    c = await asyncpg.connect(host='postgres', port=5432, user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'], database=os.environ.get('POSTGRES_DB','adventure_time'))
    print('OK', await c.fetchval('SELECT 1')); await c.close()
asyncio.run(main())
"
```

### WARN: переменная `D5f6g` is not set (или похожая)

**Причина:** в `POSTGRES_PASSWORD` есть символ **`$`**. Docker Compose воспринимает `$D5f6g` как имя переменной.

**Решение:** смените пароль **без `$`**, только буквы/цифры/`-_`:

```bash
nano .env   # POSTGRES_PASSWORD=новый_пароль_без_доллара
docker compose down
docker compose up -d --build
```

Если PostgreSQL уже создавался со старым паролем — после смены пароля может понадобиться пересоздать том (удалит данные БД):

```bash
docker compose down -v
docker compose up -d --build
```

### Участник в группе, но бот пишет «доступ не подтверждён»

**Причина:** пользователь в Telegram-группе, но **не** в таблице `approved_members` (добавлен в группу в обход бота).

**Решение:**
1. Участник проходит `/start` → заявка → владелец жмёт «Одобрить» в ЛС (`approve_user_*`).
2. Или владелец вручную синхронизирует уже одобренных через `/sync_members` (удаляет выбывших, не добавляет всех из группы автоматически).

### Бот падает на `Update | None` в main.py

**Причина:** старая версия кода без импорта `Update`. Обновите репозиторий и пересоберите:

```bash
cd /opt/bot_adventure_time
git pull
docker compose up -d --build
```

---

## Чеклист первого запуска

Идите сверху вниз — порядок совпадает с разделами §1–§7.

**§1 SSH**
- [ ] Пароль root сменён
- [ ] SSH-ключ работает, парольный вход отключён
- [ ] Пользователь `deploy` создан, работаете под ним

**§2 Сервер**
- [ ] `Europe/Helsinki`, Git установлен
- [ ] ufw + fail2ban включены
- [ ] Swap 2 ГиБ

**§3 Docker**
- [ ] `docker compose version` работает

**§4 Telegram (до деплоя)**
- [ ] Бот создан, токен сохранён
- [ ] Супергруппа с темами, бот — админ
- [ ] GROUP_ID записан
- [ ] Privacy mode выключен

**§5 Деплой**
- [ ] Репозиторий в `/opt/bot_adventure_time`
- [ ] `.env` заполнен (`TIMEZONE=Europe/Moscow`)
- [ ] `docker compose up -d` — оба контейнера Up
- [ ] В логах `Start polling`

**§6 Проверка**
- [ ] `/status`, `/menu`, `/debug_info` работают
- [ ] Одобренный участник видит команды; неодобренный в группе — сообщение о необходимости approve

**§7 Эксплуатация**
- [ ] Systemd unit включён
- [ ] Cron бэкапа настроен
- [ ] `ls -l backups/` — файлы с правами `-rw-------` (600)

---

## Приложение A — переустановка ОС на serv.host

Только если нужна другая версия Ubuntu **до** начала §1:

1. Личный кабинет → **Виртуальные серверы**
2. **⋮** → **Перейти в панель**
3. **⋮** → **Переустановить ОС**
4. **Ubuntu 22.04 LTS** или **24.04 LTS**

После переустановки fingerprint SSH изменится — подтвердите новый ключ в клиенте. Затем с §1.1.

---

## Приложение B — ресурсы и PostgreSQL

Справочно; менять ничего не нужно — уже настроено в репозитории.

**Диск (~25 ГиБ):** Ubuntu + Docker ~4–6 ГиБ, образы ~1–2 ГиБ, БД и бэкапы растут со временем. Следите: `df -h`, `docker system df`.

**RAM (~2 ГиБ):**

| Компонент | RAM |
|-----------|-----|
| PostgreSQL | ~150–300 МБ (лимит контейнера 768 МБ) |
| Бот | ~100–200 МБ (лимит 512 МБ) |
| ОС + Docker | ~300–500 МБ |
| **Итого** | ~1–1.2 ГиБ |

**PostgreSQL** (`deploy/postgresql.vds.conf` + `deploy/pg_hba.docker.conf` → `docker-compose.yml`):

- `listen_addresses='*'` **внутри контейнера** — нужно для подключения бота по имени `postgres`; снаружи порт не проброшен (`expose`, не `ports`)
- `pg_hba.docker.conf` — клиенты только с private-подсетей (10/8, 172.16/12, 192.168/16, localhost)
- `shared_buffers=128MB` — не повышать без теста
- `max_connections=20`, пул бота — до 5

**Не добавляйте** `ports: "5432:5432"` у postgres — это откроет БД на хост.
