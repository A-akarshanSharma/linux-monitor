"""CPU utilisation, load average and core counts."""

from __future__ import annotations

import psutil

from app.models import CpuMetrics


def prime_cpu_counters() -> None:
    """Start the utilisation measurement window.

    ``psutil.cpu_percent(interval=None)`` reports usage *since the previous
    call*, so the very first call always returns a meaningless 0.0. Call this
    once at start-up; every later ``collect_cpu()`` then measures the time
    elapsed since the last poll, without blocking.
    """
    psutil.cpu_percent(interval=None)


def collect_cpu() -> CpuMetrics:
    utilization = psutil.cpu_percent(interval=None)
    load_1m, load_5m, load_15m = psutil.getloadavg()
    return CpuMetrics(
        utilization_percent=min(max(utilization, 0.0), 100.0),
        load_avg_1m=load_1m,
        load_avg_5m=load_5m,
        load_avg_15m=load_15m,
        logical_cores=psutil.cpu_count(logical=True) or 1,
        physical_cores=psutil.cpu_count(logical=False),
    )
