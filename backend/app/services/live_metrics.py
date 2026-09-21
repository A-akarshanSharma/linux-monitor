"""On-demand metrics for the API.

The collectors are stateful (CPU % and network rates are measured against the
previous poll) and FastAPI runs sync endpoints on a thread pool, so requests
must not call them concurrently or in rapid succession:

* a lock serialises access, and
* a snapshot is reused for ``min_interval_seconds``, so the measurement window
  is never a few milliseconds wide (which would give noisy 0% / spiky rates)
  and a burst of requests costs one collection.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from app.collectors.snapshot import CollectionError
from app.collectors.system_info import collect_system_info
from app.config import MAX_TOP_PROCESSES
from app.models import MetricsSnapshot, SystemInfo


class SnapshotSource(Protocol):
    """What LiveMetricsService needs from a collector (satisfied by SnapshotCollector)."""

    def prime(self) -> None: ...

    def collect(self, top_processes: int | None = None) -> MetricsSnapshot: ...


class LiveMetricsService:
    def __init__(
        self,
        source: SnapshotSource,
        *,
        max_processes: int = MAX_TOP_PROCESSES,
        min_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._source = source
        self._max_processes = max_processes
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._cached: MetricsSnapshot | None = None
        self._last_sample_at: float | None = None

    def prime(self) -> None:
        """Take the baseline reading. Call once at start-up."""
        with self._lock:
            self._prime_locked()

    def _prime_locked(self) -> None:
        self._source.prime()
        self._last_sample_at = self._clock()

    def get_snapshot(self) -> MetricsSnapshot:
        """Return a snapshot at most ``min_interval_seconds`` old.

        Raises :class:`CollectionError` if collection fails; a failed attempt
        does not replace the cached snapshot.
        """
        with self._lock:
            if self._last_sample_at is None:
                self._prime_locked()
            assert self._last_sample_at is not None

            age = self._clock() - self._last_sample_at
            if self._cached is not None and age < self._min_interval:
                return self._cached
            if age < self._min_interval:
                # First reading after priming: let the measurement window fill up.
                self._sleep(self._min_interval - age)

            snapshot = self._source.collect(self._max_processes)
            self._cached = snapshot
            self._last_sample_at = self._clock()
            return snapshot

    def get_system_info(self) -> SystemInfo:
        """Fresh host identity + uptime (stateless and cheap, so never cached)."""
        try:
            return collect_system_info()
        except Exception as exc:
            raise CollectionError("system_info", exc) from exc
