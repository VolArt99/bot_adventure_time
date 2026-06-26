"""Единый реестр команд и кнопочных действий бота."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandKind(str, Enum):
    ACTION = "action"
    HELP = "help"


@dataclass(frozen=True)
class CommandSpec:
    key: str
    command: str
    description: str
    group: str
    kind: CommandKind = CommandKind.HELP
    syntax: str | None = None

    @property
    def display_syntax(self) -> str:
        return self.syntax or f"/{self.command}"


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("start", "start", "Запуск бота и онбординг.", "base", CommandKind.ACTION),
    CommandSpec("help", "help", "Подробная справка по ролям и сценариям.", "base", CommandKind.ACTION),
    CommandSpec("menu", "menu", "Главное кнопочное меню.", "base", CommandKind.ACTION),
    CommandSpec("status", "status", "Проверить, что бот онлайн.", "base", CommandKind.ACTION),
    CommandSpec("donate", "donate", "Поддержать работу бота — ссылки на сборы.", "base", CommandKind.ACTION),
    CommandSpec("create_event", "create_event", "Запустить мастер создания мероприятия.", "events", CommandKind.ACTION),
    CommandSpec("my_events", "my_events", "Открыть список ваших мероприятий.", "events", CommandKind.ACTION),
    CommandSpec("find_events", "find_events", "Поиск активных мероприятий. Пример: <code>/find_events квиз</code>", "events", CommandKind.HELP, "/find_events &lt;текст&gt;"),
    CommandSpec("set_responsible", "set_responsible", "Сменить ответственного. Пример: <code>/set_responsible 42 @ivan</code>", "events", CommandKind.HELP, "/set_responsible &lt;event_id&gt; &lt;user_id|@username&gt;"),
    CommandSpec("add_participant_manual", "add_participant_manual", "Добавить участника вручную. Пример: <code>/add_participant_manual 42 @ivan</code>", "events", CommandKind.HELP, "/add_participant_manual &lt;event_id&gt; &lt;user_id|@username&gt;"),
    CommandSpec("set_carpool_manual", "set_carpool_manual", "Ручное управление статусом карпулинга.", "events", CommandKind.HELP, "/set_carpool_manual &lt;event_id&gt; &lt;driver_id|@driver&gt; &lt;seats&gt;"),
    CommandSpec("add_passenger_manual", "add_passenger_manual", "Ручное добавление пассажира к водителю.", "events", CommandKind.HELP, "/add_passenger_manual &lt;event_id&gt; &lt;passenger_id|@passenger&gt; &lt;driver_id|@driver&gt;"),
    CommandSpec("send_event_card", "send_event_card", "Отправить короткое сообщение со ссылкой на основную карточку мероприятия.", "events", CommandKind.HELP, "/send_event_card &lt;event_id&gt;"),
    CommandSpec("edit_event", "edit_event", "Редактировать поля мероприятия. Пример: <code>/edit_event 42</code>", "events", CommandKind.HELP, "/edit_event &lt;event_id&gt;"),
    CommandSpec("digest", "digest", "Открыть общую афишу.", "digest", CommandKind.ACTION),
    CommandSpec("subscriptions", "subscriptions", "Настроить подписки и уведомления.", "digest", CommandKind.ACTION),
    CommandSpec("my_digest", "my_digest", "Получить персональный дайджест.", "digest", CommandKind.ACTION),
    CommandSpec("my_stats", "my_stats", "Посмотреть личную статистику участий.", "community", CommandKind.ACTION),
    CommandSpec("top", "top", "Показать топ активности за 30 дней.", "community", CommandKind.ACTION),
    CommandSpec("random_optin", "random_optin", "Включиться в random-встречи 1:1.", "community", CommandKind.ACTION),
    CommandSpec("random_optout", "random_optout", "Выключиться из random-встречи 1:1.", "community", CommandKind.ACTION),
    CommandSpec("split_bill", "split_bill", "Запустить мастер разделения чека.", "money", CommandKind.ACTION),
    CommandSpec("split_bill_add", "split_bill_add", "Добавить участника в чек вручную.", "money", CommandKind.HELP, "/split_bill_add &lt;id&gt; &lt;user_id|@username&gt;"),
    CommandSpec("split_bill_remove", "split_bill_remove", "Удалить участника из чека вручную.", "money", CommandKind.HELP, "/split_bill_remove &lt;id&gt; &lt;user_id|@username&gt;"),
    CommandSpec("roles", "roles", "Показать роли и лимиты.", "admin", CommandKind.ACTION),
    CommandSpec("usage_stats", "usage_stats", "Статистика использования команд.", "admin", CommandKind.ACTION),
    CommandSpec("debug_info", "debug_info", "Диагностическая сводка.", "admin", CommandKind.HELP),
    CommandSpec("list_topics", "list_topics", "Показать темы форума из БД.", "admin", CommandKind.HELP),
    CommandSpec("update_topic_names", "update_topic_names", "Синхронизировать названия тем.", "admin", CommandKind.HELP),
    CommandSpec("admin_report", "admin_report", "Управленческий отчёт по активности.", "admin", CommandKind.ACTION),
    CommandSpec("send_events_list", "send_events_list", "Опубликовать список мероприятий.", "admin", CommandKind.ACTION),
    CommandSpec("member_reengage", "member_reengage", "Отчёт по молчащим участникам.", "admin", CommandKind.HELP),
    CommandSpec("sync_members", "sync_members", "Синхронизировать локальный список участников.", "admin", CommandKind.HELP),
    CommandSpec("random_pairs", "random_pairs", "Сформировать и опубликовать пары 1:1.", "admin", CommandKind.ACTION),
    CommandSpec("pending_intro", "pending_intro", "Проверить статус рассказов о себе.", "admin", CommandKind.HELP),
    CommandSpec("random_optin_count", "random_optin_count", "Количество участников, согласных на 1:1.", "admin", CommandKind.HELP),
)

COMMANDS_BY_KEY = {spec.key: spec for spec in COMMAND_SPECS}
DEFAULT_MEMBER_ALLOWED_COMMANDS = ",".join(spec.command for spec in COMMAND_SPECS if spec.group != "admin")
