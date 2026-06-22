# Настройка VDS для Bot Adventure Time

Пошаговая инструкция от первого входа на сервер до полноценной работы бота.

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

> Полезная статья хостера про первичную настройку SSH и безопасность: [«Купили сервер. Что дальше?»](https://serv.host/articles/23/)

---

## Содержание

1. [Первый вход и безопасность SSH](#1-первый-вход-и-безопасность-ssh)
2. [Подготовка сервера](#2-подготовка-сервера)
3. [Установка Docker](#3-установка-docker)
4. [Развёртывание бота](#4-развёртывание-бота)
5. [Настройка Telegram](#5-настройка-telegram)
6. [Автозапуск и бэкапы](#6-автозапуск-и-бэкапы)
7. [Обновление бота](#7-обновление-бота)
8. [Мониторинг и диагностика](#8-мониторинг-и-диагностика)
9. [Типичные проблемы](#9-типичные-проблемы)
10. [Чеклист первого запуска](#10-чеклист-первого-запуска)

---

## 1. Первый вход и безопасность SSH

### 1.1. Данные от serv.host

После заказа VDS на почту приходит письмо с:

- **IPv4-адрес** сервера
- **логин** (обычно `root`)
- **пароль** root

Сохраните письмо в менеджере паролей, но **не оставляйте пароль из письма как единственный способ входа** — ниже настроим ключи.

### 1.2. Подключение с Windows

Рекомендуемый клиент — [MobaXterm Home Edition](https://mobaxterm.mobatek.net/download-home-edition.html) (есть встроенный SFTP).

1. **Session → SSH**
2. **Remote host** — IPv4 из письма
3. **Username** — `root`
4. **Port** — `22` (пока не меняли)
5. При первом подключении нажмите **Accept** (сохранение fingerprint сервера)
6. Вставьте пароль из письма (символы при вводе не отображаются)

Альтернатива: встроенный OpenSSH в PowerShell / Windows Terminal:

```powershell
ssh root@ВАШ_IPv4
```

### 1.3. Смена пароля root

Пароль из письма хранится у хостера и в почте — смените его сразу:

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

Если там `PasswordAuthentication yes`, правка только `sshd_config` **не сработает**.

После проверки входа по ключу:

```bash
nano /etc/ssh/sshd_config.d/50-cloud-init.conf
```

Замените:

```
PasswordAuthentication yes
```

на:

```
PasswordAuthentication no
```

Перезапуск SSH:

```bash
# Ubuntu 22.04
systemctl restart ssh

# Ubuntu 24.04 — обязательно так (иначе смена порта/настроек может не примениться):
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
```

> Подробности и скриншоты: [статья serv.host](https://serv.host/articles/23/).

### 1.6. Смена SSH-порта (опционально)

Если меняете порт (например, на `1337`), добавьте в тот же файл `50-cloud-init.conf`:

```
Port 1337
```

Перезапустите SSH (см. команды выше для вашей версии Ubuntu).

**Важно:** до перезапуска откройте новый порт в firewall:

```bash
ufw allow 1337/tcp
```

И обновите порт в MobaXterm / SSH-клиенте. Старую сессию не закрывайте, пока не убедитесь, что новый порт работает.

### 1.7. Отдельный пользователь для деплоя

Не работайте постоянно под `root`:

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Далее подключайтесь как `deploy` (с sudo при необходимости).

### 1.8. Переустановка ОС на serv.host

Если в панели при заказе была только одна версия Ubuntu:

1. Личный кабинет → **Виртуальные серверы**
2. **⋮** → **Перейти в панель**
3. **⋮** → **Переустановить ОС**
4. Выберите **Ubuntu 22.04 LTS** или **24.04 LTS**

После переустановки fingerprint SSH изменится — в клиенте подтвердите новый ключ.

---

## 2. Подготовка сервера

### 2.1. Обновление системы и часовой пояс сервера

Сервер в Финляндии — для логов ОС, cron (бэкапы) и `date` в SSH выставьте **Europe/Helsinki**:

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Europe/Helsinki
timedatectl
```

> **Не путать с `TIMEZONE` в `.env`:** там задаётся пояс для пользователей бота (даты в карточках, дайджест, напоминания). Для сообщества в Москве/СПб укажите `TIMEZONE=Europe/Moscow` — это значение по умолчанию в `bot/config.py`. Сейчас Helsinki и Moscow совпадают (UTC+3), но раздельная настройка избавит от сюрпризов, если правила DST когда-нибудь разойдутся.

### 2.2. Базовая защита (firewall, fail2ban)

Скрипт-пример: `deploy/server_hardening.example.sh`

```bash
cd /opt/bot_adventure_time   # после клонирования репозитория
# или скопируйте скрипт вручную
sudo bash deploy/server_hardening.example.sh
```

Что делает:

- **ufw** — разрешает только SSH, блокирует остальной входящий трафик
- **fail2ban** — защита от перебора SSH
- **unattended-upgrades** — автоматические security-патчи

Бот **не слушает порты** — открывать 80/443 **не нужно**.

> Anti-DDoS на стороне serv.host защищает сеть хостера; ufw дополнительно ограничивает доступ к самому серверу.

### 2.3. Swap (рекомендуется для 2 ГиБ RAM)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

Swap страхует от OOM при пиках (weekly digest, массовые напоминания).

### 2.4. Оценка места на диске (25 ГиБ)

| Компонент | Ориентир |
|-----------|----------|
| Ubuntu + Docker | ~4–6 ГиБ |
| Образы контейнеров | ~1–2 ГиБ |
| PostgreSQL + данные | растёт со временем |
| Бэкапы (`backups/`) | настраивается cron, 14 дней по умолчанию |

Периодически проверяйте: `df -h` и `docker system df`.

---

## 3. Установка Docker

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

## 4. Развёртывание бота

### 4.1. Клонирование репозитория

```bash
sudo mkdir -p /opt/bot_adventure_time
sudo chown $USER:$USER /opt/bot_adventure_time
git clone https://github.com/ВАШ_АККАУНТ/bot_adventure_time.git /opt/bot_adventure_time
cd /opt/bot_adventure_time
```

### 4.2. Создание `.env`

```bash
cp .env.example .env
nano .env
```

**Обязательные переменные:**

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от @BotFather |
| `GROUP_ID` | ID супергруппы (отрицательное число, напр. `-1001234567890`) |
| `OWNER_ID` | Ваш Telegram user ID |
| `ADMIN_IDS` | ID админов через запятую |
| `POSTGRES_PASSWORD` | Надёжный пароль для БД |
| `ENV` | `production` |
| `TIMEZONE` | `Europe/Moscow` — даты и расписание бота для участников |

**Рекомендуемые:**

| Переменная | Значение |
|------------|----------|
| `AUTO_INIT_DB` | `1` — создать таблицы при первом запуске |
| `DB_POOL_MAX_SIZE` | `5` (оптимально для 2 ГиБ RAM) |
| `WEATHER_API_KEY` | OpenWeatherMap — погода на карточках (опционально) |
| `DONATION_SBERBANK_URL` | Ссылка на сбор в Сбербанке |
| `DONATION_TBANK_URL` | Ссылка на сбор в Т-Банке |
| `OUTSIDER_ALLOWED_COMMANDS` | По умолчанию `start,donate` |

> `DATABASE_URL` для Docker Compose подставляется автоматически в `docker-compose.yml`. В `.env` достаточно `POSTGRES_PASSWORD`.

### 4.3. Первый запуск

```bash
bash deploy/deploy.sh
```

Или вручную:

```bash
docker compose build bot
docker compose up -d
```

### 4.4. Проверка логов

```bash
docker compose logs -f bot
docker compose ps
```

Успешный запуск: в логах `Start polling` без ошибок подключения к PostgreSQL.

### 4.5. PostgreSQL

Тюнинг для 2 ГиБ RAM задан в `deploy/postgresql.vds.conf` и подключается через `docker-compose.yml`:

- `shared_buffers=128MB` (не повышать до 256 МБ без теста)
- `max_connections=20` (пул бота — до 5 соединений)

### 4.6. Ресурсы контейнеров

В `docker-compose.yml` уже настроено:

- **PostgreSQL:** лимит 768 МБ
- **Бот:** лимит 512 МБ

Ориентировочный расход RAM:

| Компонент | RAM |
|-----------|-----|
| PostgreSQL | ~150–300 МБ |
| Бот (Python) | ~100–200 МБ |
| Docker + ОС | ~300–500 МБ |
| **Итого** | ~1–1.2 ГиБ из 2 ГиБ |

---

## 5. Настройка Telegram

### 5.1. Создание бота

1. Напишите @BotFather → `/newbot`
2. Скопируйте токен в `BOT_TOKEN`

### 5.2. Группа

1. Создайте **супергруппу с темами (форум)**
2. Добавьте бота **администратором** с правами:
   - удаление сообщений
   - закрепление сообщений
   - управление темами
3. Узнайте `GROUP_ID` через `/debug_info` (после запуска) или @getidsbot

### 5.3. Команды в BotFather

Отправьте @BotFather `/setcommands`:

```
start - Запуск и онбординг
help - Справка
menu - Главное меню
donate - Поддержать бота
status - Проверить работу бота
create_event - Создать мероприятие
my_events - Мои мероприятия
digest - Афиша
subscriptions - Подписки
split_bill - Разделить чек
```

> Полный список команд бот публикует сам при старте (`bot/commands.py`). Список выше — минимальный набор для меню Telegram.

### 5.4. Privacy mode

@BotFather → Bot Settings → **Group Privacy** → **Turn off**, чтобы бот видел сообщения в группе (нужно для автообнаружения тем форума).

### 5.5. Проверка после деплоя

| Действие | Ожидаемый результат |
|----------|---------------------|
| `/status` в ЛС | «Компаньон на связи» |
| `/menu` | сезонная шапка и разделы |
| `/debug_info` (админ) | корректные GROUP_ID и темы |
| Сообщение в теме форума | тема появляется в `/list_topics` |

---

## 6. Автозапуск и бэкапы

### 6.1. Systemd (автозапуск после перезагрузки)

```bash
sudo cp deploy/bot-adventure-time.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bot-adventure-time
sudo systemctl start bot-adventure-time
```

Проверка:

```bash
sudo systemctl status bot-adventure-time
```

Unit запускает `docker compose up -d` из `/opt/bot_adventure_time`. Убедитесь, что путь в файле совпадает с вашим.

### 6.2. Ежедневный бэкап БД

```bash
mkdir -p /opt/bot_adventure_time/backups
crontab -e
```

Добавьте (бэкап в 03:00 по времени **сервера** — Helsinki, хранение 14 дней — встроено в скрипт):

```
0 3 * * * /opt/bot_adventure_time/deploy/backup_db.sh >> /opt/bot_adventure_time/backups/backup.log 2>&1
```

Ручной бэкап:

```bash
bash deploy/backup_db.sh
ls -lh backups/
```

### 6.3. Восстановление из бэкапа

```bash
gunzip -c backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U bot adventure_time
```

---

## 7. Обновление бота

```bash
cd /opt/bot_adventure_time
git pull
bash deploy/deploy.sh
```

Проверка:

```bash
docker compose logs --tail=50 bot
```

---

## 8. Мониторинг и диагностика

### 8.1. Логи

```bash
# Бот
docker compose logs -f bot

# PostgreSQL
docker compose logs -f postgres
```

В логах бота:

- `slow_pg_query_ms` — медленные запросы (>300 мс)
- `update_processing` / `pg_query` — p50/p95/p99 латентности

### 8.2. Команды в Telegram

| Команда | Кто | Что делает |
|---------|-----|------------|
| `/status` | Все | Бот онлайн |
| `/menu` | Участник | Control Center |
| `/donate` | Все в ЛС | Ссылки на сборы |
| `/debug_info` | Админ | Диагностика бота, группы, тем |
| `/usage_stats` | Админ | Статистика команд |

### 8.3. Ресурсы сервера

```bash
htop          # RAM и CPU
df -h         # диск
docker stats  # контейнеры
free -h       # swap
```

### 8.4. Перезапуск

```bash
docker compose restart bot
# полный перезапуск:
docker compose down && docker compose up -d
```

---

## 9. Типичные проблемы

### Бот не отвечает

1. `docker compose ps` — контейнер `bot` в статусе `Up`?
2. `docker compose logs bot` — ошибки токена, GROUP_ID, БД?
3. Проверьте `BOT_TOKEN` в `.env`

### Ошибка подключения к PostgreSQL

1. `docker compose ps` — `postgres` healthy?
2. `POSTGRES_PASSWORD` совпадает в `.env`?
3. Подождите 10–15 сек после `up -d` (healthcheck)

### GROUP_ID обязателен

В production (`ENV=production`) бот не запустится без `GROUP_ID`.

### Нехватка памяти (OOM)

1. `docker stats` и `free -h`
2. Убедитесь, что swap включён (раздел 2.3)
3. Лимиты в `docker-compose.yml` уже ограничивают контейнеры

### Бот не видит темы форума

1. Privacy mode выключен в BotFather
2. Отправьте сообщение в тему — бот обнаружит её автоматически
3. `/list_topics` — проверка тем в БД

### Не получается отключить SSH-пароль

Проверьте `/etc/ssh/sshd_config.d/50-cloud-init.conf`, а не только `sshd_config`. См. [статью serv.host](https://serv.host/articles/23/).

### Сменили SSH-порт на Ubuntu 24.04 — не подключается

Используйте:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
```

### Пожертвования не работают

В `.env` задайте:

```
DONATION_SBERBANK_URL=https://...
DONATION_TBANK_URL=https://...
```

---

## 10. Чеклист первого запуска

- [ ] Письмо serv.host сохранено, пароль root сменён
- [ ] SSH-ключ настроен, вход по паролю отключён (`50-cloud-init.conf`)
- [ ] Создан пользователь `deploy` (или аналог)
- [ ] Firewall (ufw) включён, открыт только SSH
- [ ] Swap 2 ГиБ включён
- [ ] Часовой пояс сервера `Europe/Helsinki` (`timedatectl`)
- [ ] В `.env`: `TIMEZONE=Europe/Moscow`
- [ ] Docker установлен
- [ ] Репозиторий в `/opt/bot_adventure_time`
- [ ] `.env` заполнен (токен, GROUP_ID, пароль БД)
- [ ] `docker compose up -d` — оба контейнера работают
- [ ] Бот добавлен в группу как админ, privacy mode выключен
- [ ] `/debug_info` показывает корректные данные
- [ ] `/menu` и `/status` работают
- [ ] Systemd unit включён
- [ ] Cron для бэкапов настроен
