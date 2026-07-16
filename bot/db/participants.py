"""Event participants and carpool management."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .events import get_event
from .ids import next_id
from ._core import _run_execute, _run_query

_MAIN_STATUSES = ("going", "driver", "passenger", "ride_seeker")
_MAIN_STATUS_SQL = "'going', 'driver', 'passenger', 'ride_seeker'"


async def get_occupied_seats(event_id: int) -> int:
    """Сколько мест занято основным составом (участник + гости)."""
    result = await _run_query(
        f"""
        SELECT COALESCE(SUM(1 + COALESCE(guest_count, 0)), 0)::bigint AS occupied
        FROM participants
        WHERE event_id = $event_id
          AND status IN ({_MAIN_STATUS_SQL})
        """,
        parameters={"event_id": int(event_id)},
    )
    if not result[0].rows:
        return 0
    return int(result[0].rows[0].occupied or 0)


async def get_main_guest_counts(event_id: int) -> Dict[int, int]:
    """user_id → число гостей для основного состава."""
    result = await _run_query(
        f"""
        SELECT user_id, COALESCE(guest_count, 0)::bigint AS guest_count
        FROM participants
        WHERE event_id = $event_id
          AND status IN ({_MAIN_STATUS_SQL})
        """,
        parameters={"event_id": int(event_id)},
    )
    return {
        int(row.user_id): int(row.guest_count or 0)
        for row in result[0].rows
        if int(row.guest_count or 0) > 0
    }


async def set_participant_guest_count(event_id: int, user_id: int, guest_count: int) -> str:
    """
    Устанавливает число гостей у участника основного состава.

    Возвращает: ok | not_participant | full | invalid
    """
    if guest_count < 0:
        return "invalid"

    result = await _run_query(
        """
        SELECT status, COALESCE(guest_count, 0)::bigint AS guest_count
        FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={"event_id": int(event_id), "user_id": int(user_id)},
    )
    if not result[0].rows:
        return "not_participant"

    status = str(result[0].rows[0].status)
    if status not in _MAIN_STATUSES:
        return "not_participant"

    old_guests = int(result[0].rows[0].guest_count or 0)
    event = await get_event(event_id)
    if not event:
        return "invalid"

    limit = int(event.get("participant_limit") or 0)
    if limit > 0 and guest_count != old_guests:
        occupied = await get_occupied_seats(event_id)
        new_occupied = occupied - old_guests + guest_count
        if new_occupied > limit:
            return "full"

    await _run_query(
        """
        UPDATE participants
        SET guest_count = $guest_count
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": int(event_id),
            "user_id": int(user_id),
            "guest_count": int(guest_count),
        },
    )
    return "ok"


async def add_participant(
    event_id: int,
    user_id: int,
    status: str = "going",
    car_seats: int = None,
    passenger_of: int = None,
) -> bool:
    """Добавляет участника атомарно (UNIQUE + capacity check для основного состава)."""
    participant_id = await next_id("participants_id_seq")
    joined_at = datetime.now(timezone.utc)
    enforce_capacity = status in _MAIN_STATUSES

    if enforce_capacity:
        result = await _run_query(
            f"""
            INSERT INTO participants (
                id, event_id, user_id, status, car_seats, passenger_of, guest_count, joined_at
            )
            SELECT
                $id, $event_id, $user_id, $status, $car_seats, $passenger_of, 0, $joined_at
            WHERE
                COALESCE((SELECT participant_limit FROM events WHERE id = $event_id), 0) <= 0
                OR (
                    SELECT COALESCE(SUM(1 + COALESCE(guest_count, 0)), 0)::bigint
                    FROM participants
                    WHERE event_id = $event_id
                      AND status IN ({_MAIN_STATUS_SQL})
                ) < COALESCE((SELECT participant_limit FROM events WHERE id = $event_id), 0)
            ON CONFLICT (event_id, user_id) DO NOTHING
            RETURNING id
            """,
            parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "status": status,
                "car_seats": car_seats or 0,
                "passenger_of": passenger_of or 0,
                "joined_at": joined_at,
            },
        )
    else:
        result = await _run_query(
            """
            INSERT INTO participants (
                id, event_id, user_id, status, car_seats, passenger_of, guest_count, joined_at
            ) VALUES (
                $id, $event_id, $user_id, $status, $car_seats, $passenger_of, 0, $joined_at
            )
            ON CONFLICT (event_id, user_id) DO NOTHING
            RETURNING id
            """,
            parameters={
                "id": participant_id,
                "event_id": int(event_id),
                "user_id": int(user_id),
                "status": status,
                "car_seats": car_seats or 0,
                "passenger_of": passenger_of or 0,
                "joined_at": joined_at,
            },
        )

    return bool(result[0].rows)


async def remove_participant(event_id: int, user_id: int) -> bool:
    """Удаляет участника из события (и пассажиров если водитель).

    Возвращает True, если участник был в списке до удаления.
    """
    result = await _run_query(
        """
        SELECT status FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": event_id,
            "user_id": user_id,
        },
    )

    if not result[0].rows:
        return False

    status = result[0].rows[0].status
    if status == "driver":
        await _run_query(
            """
            DELETE FROM participants
            WHERE event_id = $event_id AND passenger_of = $driver_id
            """,
            parameters={
                "event_id": event_id,
                "driver_id": user_id,
            },
        )

    await _run_query(
        """
        DELETE FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": event_id,
            "user_id": user_id,
        },
    )
    return True


async def get_participants(event_id: int, status: str = None) -> List[int]:
    """Возвращает список ID участников с указанным статусом."""
    if status:
        query = """
            SELECT user_id FROM participants
            WHERE event_id = $event_id AND status = $status
        """
        params = {
            "event_id": event_id,
            "status": status,
        }
    else:
        query = """
            SELECT user_id FROM participants
            WHERE event_id = $event_id
        """
        params = {
            "event_id": event_id,
        }

    result = await _run_query(
        query,
        parameters=params,
    )

    return [row.user_id for row in result[0].rows]


async def get_main_participants(event_id: int) -> List[int]:
    """Возвращает ID участников основного состава (идут + карпулинг + ищут попутку)."""
    result = await _run_query(
        """
        SELECT DISTINCT user_id FROM participants
        WHERE event_id = $event_id AND status IN ('going', 'driver', 'passenger', 'ride_seeker')
        """,
        parameters={
            "event_id": event_id,
        },
    )

    return [row.user_id for row in result[0].rows]


async def get_ride_seekers(event_id: int) -> List[int]:
    """Участники, которые ищут попутку (без роли водителя/пассажира)."""
    result = await _run_query(
        """
        SELECT user_id FROM participants
        WHERE event_id = $event_id AND status = 'ride_seeker'
        ORDER BY joined_at
        """,
        parameters={"event_id": int(event_id)},
    )
    return [int(row.user_id) for row in result[0].rows]


async def toggle_ride_seeker(event_id: int, user_id: int) -> str:
    """Переключает статус «ищу попутку». Возвращает: added, removed, denied, full."""
    result = await _run_query(
        """
        SELECT status FROM participants
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={"event_id": int(event_id), "user_id": int(user_id)},
    )
    if result[0].rows:
        status = str(result[0].rows[0].status)
        if status in {"driver", "passenger"}:
            return "denied"
        if status == "ride_seeker":
            await _run_query(
                """
                UPDATE participants SET status = 'going'
                WHERE event_id = $event_id AND user_id = $user_id
                """,
                parameters={"event_id": int(event_id), "user_id": int(user_id)},
            )
            return "removed"
        if status == "going":
            await _run_query(
                """
                UPDATE participants SET status = 'ride_seeker'
                WHERE event_id = $event_id AND user_id = $user_id
                """,
                parameters={"event_id": int(event_id), "user_id": int(user_id)},
            )
            return "added"

    event = await get_event(event_id)
    if not event:
        return "denied"
    participant_limit = event.get("participant_limit") or 0
    if participant_limit > 0:
        occupied = await get_occupied_seats(event_id)
        if occupied >= participant_limit:
            return "full"

    created = await add_participant(event_id, user_id, "ride_seeker")
    return "added" if created else "denied"


async def move_from_waitlist(event_id: int) -> Optional[int]:
    """Перемещает первого из резерва в основной список."""
    event = await get_event(event_id)
    if not event:
        return None

    participant_limit = event.get("participant_limit") or 0
    if participant_limit > 0:
        occupied = await get_occupied_seats(event_id)
        if occupied >= participant_limit:
            return None

    result = await _run_query(
        """
        SELECT user_id FROM participants
        WHERE event_id = $event_id AND status = 'waitlist'
        ORDER BY joined_at
        LIMIT 1
        """,
        parameters={
            "event_id": event_id,
        },
    )

    if not result[0].rows:
        return None

    user_id = result[0].rows[0].user_id

    await _run_query(
        """
        UPDATE participants
        SET status = 'going', guest_count = 0
        WHERE event_id = $event_id AND user_id = $user_id
        """,
        parameters={
            "event_id": event_id,
            "user_id": user_id,
        },
    )

    return user_id


async def get_drivers_with_passengers(event_id: int) -> List[Dict]:
    """Возвращает список водителей с их пассажирами."""
    result_drivers = await _run_query(
        """
        SELECT user_id, car_seats FROM participants
        WHERE event_id = $event_id AND status = 'driver'
        """,
        parameters={
            "event_id": event_id,
        },
    )

    drivers = []
    for row in result_drivers[0].rows:
        driver_id = row.user_id
        car_seats = row.car_seats

        result_passengers = await _run_query(
            """
            SELECT user_id FROM participants
            WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
            """,
            parameters={
                "event_id": event_id,
                "driver_id": driver_id,
            },
        )

        passengers = [
            row_passenger.user_id for row_passenger in result_passengers[0].rows
        ]

        drivers.append(
            {
                "user_id": driver_id,
                "car_seats": car_seats,
                "passengers": passengers,
            }
        )

    return drivers


async def get_driver_free_seats(driver_id: int, event_id: int) -> int:
    """Возвращает количество свободных мест у водителя."""
    result_driver = await _run_query(
        """
        SELECT car_seats FROM participants
        WHERE event_id = $event_id AND user_id = $driver_id AND status = 'driver'
        """,
        parameters={
            "event_id": event_id,
            "driver_id": driver_id,
        },
    )

    if not result_driver[0].rows:
        return 0

    car_seats = result_driver[0].rows[0].car_seats

    result_passengers = await _run_query(
        """
        SELECT COUNT(*) as passenger_count FROM participants
        WHERE event_id = $event_id AND status = 'passenger' AND passenger_of = $driver_id
        """,
        parameters={
            "event_id": event_id,
            "driver_id": driver_id,
        },
    )

    passenger_count = (
        result_passengers[0].rows[0].passenger_count if result_passengers[0].rows else 0
    )

    free_seats = car_seats - passenger_count - 1
    return max(0, free_seats)


async def set_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Атомарно назначает пользователя водителем (UPSERT по UNIQUE)."""
    participant_id = await next_id("participants_id_seq")
    joined_at = datetime.now(timezone.utc)
    await _run_execute(
        """
        INSERT INTO participants (
            id, event_id, user_id, status, car_seats, passenger_of, joined_at
        ) VALUES (
            $id, $event_id, $user_id, 'driver', $car_seats, 0, $joined_at
        )
        ON CONFLICT (event_id, user_id) DO UPDATE
        SET status = 'driver',
            car_seats = EXCLUDED.car_seats,
            passenger_of = 0
        """,
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "car_seats": int(car_seats),
            "joined_at": joined_at,
        },
    )
    return True


async def set_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Атомарно назначает пользователя пассажиром выбранного водителя."""
    free_seats = await get_driver_free_seats(driver_id, event_id)
    if free_seats <= 0:
        return False
    participant_id = await next_id("participants_id_seq")
    joined_at = datetime.now(timezone.utc)
    await _run_execute(
        """
        INSERT INTO participants (
            id, event_id, user_id, status, car_seats, passenger_of, joined_at
        ) VALUES (
            $id, $event_id, $user_id, 'passenger', 0, $driver_id, $joined_at
        )
        ON CONFLICT (event_id, user_id) DO UPDATE
        SET status = 'passenger',
            car_seats = 0,
            passenger_of = EXCLUDED.passenger_of
        """,
        parameters={
            "id": participant_id,
            "event_id": int(event_id),
            "user_id": int(user_id),
            "driver_id": int(driver_id),
            "joined_at": joined_at,
        },
    )
    return True


async def add_driver(event_id: int, user_id: int, car_seats: int) -> bool:
    """Добавляет или обновляет водителя."""
    return await set_driver(event_id, user_id, car_seats)


async def add_passenger(event_id: int, user_id: int, driver_id: int) -> bool:
    """Добавляет или обновляет пассажира к водителю."""
    return await set_passenger(event_id, user_id, driver_id)
