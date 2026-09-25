"""On-demand read access to the scheduler's latest snapshot, for the API layer.

The scheduler (not this class) owns collection and its locking; this is a thin,
stateless facade so the API routes have a small, mockable dependency instead of
reaching into ``app.state.scheduler`` directly.
"""

from __future__ import annotations

from collections.abc import Callable

from app.collectors.snapshot import CollectionError
from app.collectors.system_info import collect_system_info
from app.models import MetricsSnapshot, SystemInfo


class LiveMetricsService:
    def __init__(self, latest_snapshot: Callable[[], MetricsSnapshot]) -> None:
        self._latest_snapshot = latest_snapshot

    def get_snapshot(self) -> MetricsSnapshot:
        """Raises :class:`CollectionError` (-> 503) if nothing has been collected yet."""
        return self._latest_snapshot()

    def get_system_info(self) -> SystemInfo:
        """Host identity is cheap and stateless, so it is always collected fresh
        rather than read from the scheduler's periodic snapshot."""
        try:
            return collect_system_info()
        except Exception as exc:
            raise CollectionError("system_info", exc) from exc
