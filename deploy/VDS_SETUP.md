# Настройка VDS для Bot Adventure Time

Пошаговая инструкция для сервера с характеристиками:
- **CPU:** 1 vCPU (AMD EPYC)
- **RAM:** 2 ГиБ
- **Диск:** 25 ГиБ NVMe
- **Сеть:** 250 Мбит/с (burst до 1 Гбит/с)
- **Локация:** Финляндия
- **IPv4:** 1 адрес, IPv6 /64

Бот работает в **polling-режиме** (исходящие запросы к Telegram API). Входящие HTTP-порты не нужны.

---

## Содержание

1. [Первичная настройка сервера](#1-первичная-настройка-сервера)
2. [Установка Docker](#2-установка-docker)
3. [Развёртывание бота](#3-развёртывание-бота)
4. [Настройка Telegram](#4-настройка-telegram)
5. [Автозапуск и бэкапы](#5-автозапуск-и-бэкапы)
6. [Обновление бота](#6-обновление-бота)
7. [Мониторинг и диагностика](#7-мониторинг-и-диагностика)
8. [Типичные проблемы](#8-типичные-проблемы)

---

## 1. Первичная настройка сервера

### 1.1. Подключение по SSH

```bash
ssh root@ВАШ_IPv4
```

Рекомендуется сразу создать отдельного пользователя:

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Далее работайте под `deploy` (или своим пользователем с sudo).

### 1.2. Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Europe/Helsinki
```

### 1.3. Базовая защита (firewall)

Скрипт-пример: `deploy/server_hardening.example.sh`

```bash
sudo bash deploy/server_hardening.example.sh
```

Что делает:
- **ufw** — разрешает только SSH (порт 22), блокирует входящий трафик на остальные порты
- **fail2ban** — защита от перебора паролей SSH
- **unattended-upgrades** — автоматические security-патчи

> Бот не слушает порты — открывать 80/443 **не нужно**.

### 1.4. Swap (рекомендуется для 2 ГиБ RAM)

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Swap страхует от OOM при пиковых нагрузках (дайджест, массовая рассылка).

---

## 2. Установка Docker

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

## 3. Развёртывание бота

### 3.1. Клонирование репозитория

```bash
sudo mkdir -p /opt/bot_adventure_time
sudo chown $USER:$USER /opt/bot_adventure_time
git clone https://github.com/ВАШ_АККАУНТ/bot_adventure_time.git /opt/bot_adventure_time
cd /opt/bot_adventure_time
```

### 3.2. Создание `.env`

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
| `TIMEZONE` | `Europe/Helsinki` (Финляндия) или `Europe/Moscow` |

**Рекомендуемые:**

| Переменная | Значение |
|------------|----------|
| `AUTO_INIT_DB` | `1` — создать таблицы при первом запуске |
| `DB_POOL_MAX_SIZE` | `5` (по умолчанию, оптимально для 2 ГиБ) |
| `DONATION_SBERBANK_URL` | Ссылка на сбор в Сбербанке |
| `DONATION_TBANK_URL` | Ссылка на сбор в Т-Банке |

### 3.3. Первый запуск

```bash
bash deploy/deploy.sh
```

Или вручную:

```bash
docker compose build bot
docker compose up -d
```

### 3.4. Проверка логов

```bash
docker compose logs -f bot
docker compose ps
```

Успешный запуск: в логах `Start polling` без ошибок подключения к PostgreSQL.

| `WEATHER_API_KEY` | Погода на карточках (опционально) |
| `OUTSIDER_ALLOWED_COMMANDS` | По умолчанию `start,donate` |

### 3.5. PostgreSQL

Тюнинг для 2 ГиБ RAM задан в `deploy/postgresql.vds.conf` и подключается через `docker-compose.yml`:
- `shared_buffers=128MB` (не повышать до 256 МБ без теста)
- `max_connections=20` (пул бота — 5 соединений)

### 3.6. Ресурсы контейнеров

В `docker-compose.yml` уже настроено:
- **PostgreSQL:** лимит 768 МБ, тюнинг из `deploy/postgresql.vds.conf`
- **Бот:** лимит 512 МБ

Ориентировочный расход RAM:
| Компонент | RAM |
|-----------|-----|
| PostgreSQL | ~150–300 МБ |
| Бот (Python) | ~100–200 МБ |
| Docker + ОС | ~300–500 МБ |
| **Итого** | ~1–1.2 ГиБ из 2 ГиБ |

---

## 4. Настройка Telegram

### 4.1. Создание бота

1. Напишите @BotFather → `/newbot`
2. Скопируйте токен в `BOT_TOKEN`

### 4.2. Группа

1. Создайте супергруппу с **темами (форум)**
2. Добавьте бота как **администратора** с правами:
   - Удаление сообщений
   - Закрепление сообщений
   - Управление темами
3. Узнайте `GROUP_ID` через `/debug_info` (после запуска) или @getidsbot

### 4.3. Команды бота в BotFather

Отправьте @BotFather список команд (или `/setcommands`):

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

### 4.4. Privacy mode

В @BotFather → Bot Settings → **Group Privacy** → **Turn off**, чтобы бот видел сообщения в группе (для обнаружения тем форума).

---

## 5. Автозапуск и бэкапы

### 5.1. Systemd (автозапуск после перезагрузки)

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

### 5.2. Ежедневный бэкап БД

```bash
crontab -e
```

Добавьте строку (бэкап в 03:00, хранение 14 дней — встроено в скрипт):

```
0 3 * * * /opt/bot_adventure_time/deploy/backup_db.sh >> /opt/bot_adventure_time/backups/backup.log 2>&1
```

Ручной бэкап:

```bash
bash deploy/backup_db.sh
ls -lh backups/
```

### 5.3. Восстановление из бэкапа

```bash
gunzip -c backups/adventure_time_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U bot adventure_time
```

---

## 6. Обновление бота

```bash
cd /opt/bot_adventure_time
git pull
bash deploy/deploy.sh
```

Проверка после обновления:

```bash
docker compose logs --tail=50 bot
```

---

## 7. Мониторинг и диагностика

### 7.1. Логи

```bash
# Бот
docker compose logs -f bot

# PostgreSQL
docker compose logs -f postgres

# Медленные запросы (>300 мс) — в логах бота: slow_pg_query_ms
# Латентность обработки — latency_metrics
```

### 7.2. Команды в Telegram

| Команда | Кто | Что делает |
|---------|-----|------------|
| `/status` | Все | Бот онлайн («Компаньон на связи») |
| `/menu` | Участник | Control Center с сезонной шапкой |
| `/donate` | Все в ЛС | Ссылки на сборы |
| `/debug_info` | Админ | Диагностика бота, группы, тем |
| `/usage_stats` | Админ | Статистика команд |

### 7.3. Ресурсы сервера

```bash
# RAM и CPU
htop

# Диск
df -h

# Docker
docker stats
```

### 7.4. Перезапуск

```bash
docker compose restart bot
# или полный перезапуск:
docker compose down && docker compose up -d
```

---

## 8. Типичные проблемы

### Бот не отвечает

1. `docker compose ps` — контейнер `bot` в статусе `Up`?
2. `docker compose logs bot` — ошибки токена, GROUP_ID, БД?
3. Проверьте `BOT_TOKEN` в `.env`

### Ошибка подключения к PostgreSQL

1. `docker compose ps` — `postgres` healthy?
2. `POSTGRES_PASSWORD` совпадает в `.env` и `DATABASE_URL`?
3. Подождите 10–15 сек после `up -d` (healthcheck)

### GROUP_ID обязателен

В production (`ENV=production`) бот не запустится без `GROUP_ID`. Укажите ID супергруппы.

### Нехватка памяти (OOM)

1. Проверьте `docker stats` и `free -h`
2. Убедитесь, что swap включён (раздел 1.4)
3. Лимиты в docker-compose уже ограничивают контейнеры

### Бот не видит темы форума

1. Privacy mode выключен в BotFather
2. Отправьте сообщение в тему — бот автоматически обнаружит её
3. `/list_topics` — проверка тем в БД

### Пожертвования не работают

Убедитесь, что в `.env` заданы:
```
DONATION_SBERBANK_URL=https://...
DONATION_TBANK_URL=https://...
```

Команда `/donate` доступна всем в ЛС (включая не-участников группы).

---

## Чеклист первого запуска

- [ ] SSH доступ настроен, firewall включён
- [ ] Docker установлен
- [ ] Репозиторий склонирован в `/opt/bot_adventure_time`
- [ ] `.env` заполнен (токен, GROUP_ID, пароль БД)
- [ ] `docker compose up -d` — оба контейнера работают
- [ ] Бот добавлен в группу как админ
- [ ] `/debug_info` показывает корректные данные
- [ ] `/menu` показывает сезон и слоган
- [ ] `/donate` показывает кнопки сборов (если URL заданы)
- [ ] Одобрение заявки — текст `🎉🗺️ Дверь открыта!`
- [ ] Systemd unit включён
- [ ] Cron для бэкапов настроен
- [ ] Ссылки на сборы в `.env` заполнены
