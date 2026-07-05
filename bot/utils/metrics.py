import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class LatencyMetrics:
    """Simple in-memory latency collector with percentile logging."""

    def __init__(self, name: str, window_size: int = 1000, log_every: int = 100) -> None:
        self.name = name
        self._samples = deque(maxlen=window_size)
        self._log_every = log_every
        self._count = 0
        self._lock = asyncio.Lock()

    @staticmethod
    def _percentile(sorted_values: list[float], q: float) -> float:
        if not sorted_values:
            return 0.0
        idx = max(0, min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * q))))
        return sorted_values[idx]

    async def observe(self, duration_seconds: float) -> None:
        async with self._lock:
            self._samples.append(duration_seconds)
            self._count += 1
            if self._count % self._log_every != 0:
                return

            snapshot = self._build_snapshot_locked()
            logger.info(
                "latency_metrics name=%s samples=%s p50_ms=%.2f p95_ms=%.2f p99_ms=%.2f",
                snapshot["name"],
                snapshot["samples"],
                snapshot["p50_ms"],
                snapshot["p95_ms"],
                snapshot["p99_ms"],
            )

    def _build_snapshot_locked(self) -> dict[str, float | int | str]:
        values = sorted(self._samples)
        return {
            "name": self.name,
            "samples": len(values),
            "p50_ms": self._percentile(values, 0.50) * 1000,
            "p95_ms": self._percentile(values, 0.95) * 1000,
            "p99_ms": self._percentile(values, 0.99) * 1000,
        }

    async def snapshot(self) -> dict[str, float | int | str]:
        async with self._lock:
            return self._build_snapshot_locked()


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._start
