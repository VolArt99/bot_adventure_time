"""Runtime flags for safe startup behavior in different environments."""

from __future__ import annotations

import os


def _parse_auto_init_db(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def should_run_schema_init() -> bool:
    """Return whether `init_db()` should run during process startup."""
    override = _parse_auto_init_db(os.getenv("AUTO_INIT_DB"))
    if override is not None:
        return override
    return True


def should_run_schema_init_webhook() -> bool:
    """Return whether `init_db()` should run in webhook/serverless handlers."""
    override = _parse_auto_init_db(os.getenv("AUTO_INIT_DB"))
    if override is not None:
        return override
    return False
