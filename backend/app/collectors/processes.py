"""Process count and top consumers by CPU and memory."""

from __future__ import annotations

import heapq
from typing import Any

import psutil

from app.models import ProcessInfo, ProcessMetrics

# Command lines are deliberately NOT collected: they routinely contain
# passwords / tokens passed as arguments.
_ATTRS = ["pid", "name", "username", "status", "cpu_percent", "memory_percent", "memory_info"]


def prime_process_cpu() -> None:
    """Start per-process CPU measurement windows (see ``prime_cpu_counters``).

    ``psutil.process_iter`` caches Process objects between calls, which is what
    makes ``cpu_percent`` meaningful on later iterations.
    """
    for _ in psutil.process_iter(["cpu_percent"]):
        pass


def _to_model(info: dict[str, Any]) -> ProcessInfo:
    # Fields are None when access was denied (e.g. another user's process).
    memory_info = info.get("memory_info")
    return ProcessInfo(
        pid=info["pid"],
        name=info.get("name") or "unknown",
        username=info.get("username"),
        status=info.get("status") or "unknown",
        cpu_percent=info.get("cpu_percent") or 0.0,
        memory_percent=round(info.get("memory_percent") or 0.0, 2),
        memory_rss_bytes=memory_info.rss if memory_info else 0,
    )


def collect_processes(top_n: int = 5) -> ProcessMetrics:
    processes: list[ProcessInfo] = []
    running = 0
    for proc in psutil.process_iter(_ATTRS):  # vanished processes are skipped by psutil
        info = proc.info
        if info.get("status") == psutil.STATUS_RUNNING:
            running += 1
        processes.append(_to_model(info))

    return ProcessMetrics(
        total_count=len(processes),
        running_count=running,
        top_by_cpu=heapq.nlargest(top_n, processes, key=lambda p: p.cpu_percent),
        top_by_memory=heapq.nlargest(top_n, processes, key=lambda p: p.memory_rss_bytes),
    )
