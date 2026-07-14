"""Safe ID generation via PostgreSQL sequences."""

from __future__ import annotations

from bot.db_pool import execute, fetchval

_SEQUENCES = frozenset({
    "events_id_seq",
    "participants_id_seq",
    "split_bill_events_id_seq",
    "pending_notifications_id_seq",
})

_SEQUENCE_BOOTSTRAP = (
    ("events_id_seq", "events"),
    ("participants_id_seq", "participants"),
    ("split_bill_events_id_seq", "split_bill_events"),
    ("pending_notifications_id_seq", "pending_notifications"),
)


async def ensure_id_sequences() -> None:
    """Creates sequences and aligns them to existing MAX(id)."""
    for seq_name, table_name in _SEQUENCE_BOOTSTRAP:
        await execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
        try:
            max_id = await fetchval(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
        except Exception:
            max_id = 0
        max_id = int(max_id or 0)
        # is_called=True when table already has rows, so nextval returns max+1
        is_called = "true" if max_id > 0 else "false"
        start_value = max(max_id, 1)
        await execute(f"SELECT setval('{seq_name}', {start_value}, {is_called})")


async def next_id(sequence_name: str) -> int:
    """Returns the next value from a sequence."""
    if sequence_name not in _SEQUENCES:
        raise ValueError(f"Unknown sequence: {sequence_name}")
    value = await fetchval(f"SELECT nextval('{sequence_name}')")
    return int(value)
