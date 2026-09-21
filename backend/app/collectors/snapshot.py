"""Aggregates every collector into one timestamped snapshot."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from app.collectors.cpu import collect_cpu, prime_cpu_counters
from app.collectors.disk import collect_disks
from app.collectors.memory import collect_memory
from app.collectors.network import NetworkCollector
from app.collectors.processes import collect_processes, prime_process_cpu
from app.collectors.system_info import collect_system_info
from app.config import Settings, get_settings
from app.models import MetricsSnapshot

T = TypeVar("T")


class CollectionError(RuntimeError):
    """Raised when one of the collectors fails; names the failing collector."""

    def __init__(self, collector: str, cause: Exception) -> None:
        super().__init__(f"{collector} collector failed: {cause}")
        self.collector = collector


def _run(name: str, func: Callable[[], T]) -> T:
    try:
        return func()
    except Exception as exc:
        raise CollectionError(name, exc) from exc


class SnapshotCollector:
    """Stateful collector: keep one instance for the lifetime of the agent.

    State is needed for rate-style metrics (CPU %, network bytes/sec), which
    are computed relative to the previous poll.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._network = NetworkCollector()

    def prime(self) -> None:
        """Take the baseline readings that later rate calculations compare against."""
        prime_cpu_counters()
        prime_process_cpu()
        self._network.collect()

    def collect(self) -> MetricsSnapshot:
        """Collect a full snapshot. Raises :class:`CollectionError` on failure."""
        s = self._settings
        return MetricsSnapshot(
            collected_at=datetime.now(timezone.utc),
            system=_run("system_info", collect_system_info),
            cpu=_run("cpu", collect_cpu),
            memory=_run("memory", collect_memory),
            disks=_run("disk", lambda: collect_disks(s.disk_exclude_fstypes)),
            network=_run("network", self._network.collect),
            processes=_run("processes", lambda: collect_processes(s.top_processes_count)),
        )
