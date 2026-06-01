"""Единая политика завершения callback-хендлеров.

Правило удаления сообщений бота:
- CALLBACK_DELETE_WIZARD_MESSAGE=True — шаговые меню в ЛС/FSM wizard flows,
  где старое меню должно исчезнуть после выбора.
- CALLBACK_KEEP_PUBLIC_MESSAGE=False — callbacks меню/карточек, где сообщение
  должно оставаться на месте или редактироваться независимо от типа чата.
"""

CALLBACK_DELETE_WIZARD_MESSAGE = True
CALLBACK_KEEP_PUBLIC_MESSAGE = False
