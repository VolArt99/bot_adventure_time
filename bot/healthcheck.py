"""CLI healthcheck for Docker (exit 0 = healthy)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_AGE_SECONDS = int(os.getenv("BOT_HEARTBEAT_MAX_AGE_SECONDS", "120"))
HEARTBEAT_PATH = Path(os.getenv("BOT_HEARTBEAT_PATH", "/tmp/bot_heartbeat"))


def main() -> int:
    if not HEARTBEAT_PATH.exists():
        print(f"heartbeat missing: {HEARTBEAT_PATH}", file=sys.stderr)
        return 1
    age = (
        datetime.now(timezone.utc)
        - datetime.fromtimestamp(HEARTBEAT_PATH.stat().st_mtime, timezone.utc)
    ).total_seconds()
    if age > MAX_AGE_SECONDS:
        print(f"heartbeat stale: age={age:.0f}s max={MAX_AGE_SECONDS}s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
