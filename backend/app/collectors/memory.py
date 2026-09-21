"""RAM and swap usage."""

from __future__ import annotations

import psutil

from app.models import MemoryMetrics


def collect_memory() -> MemoryMetrics:
    """Collect RAM and swap usage.

    ``ram_percent`` is based on *available* memory (what applications can still
    obtain, including reclaimable page cache) rather than *free* memory, which
    on Linux is almost always small and would cause false alarms.
    """
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return MemoryMetrics(
        ram_total_bytes=ram.total,
        ram_used_bytes=ram.used,
        ram_available_bytes=ram.available,
        ram_percent=ram.percent,
        swap_total_bytes=swap.total,
        swap_used_bytes=swap.used,
        swap_percent=swap.percent,
    )
