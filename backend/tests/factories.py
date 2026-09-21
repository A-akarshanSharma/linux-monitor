"""Builders for canned test data, so API tests don't depend on the real machine."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import (
    CpuMetrics,
    DiskUsage,
    MemoryMetrics,
    MetricsSnapshot,
    NetworkInterface,
    NetworkMetrics,
    ProcessInfo,
    ProcessMetrics,
    SystemInfo,
)

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def make_system_info(**overrides: object) -> SystemInfo:
    data = {
        "hostname": "test-host",
        "ip_address": "10.0.0.5",
        "os_name": "Ubuntu 24.04 LTS",
        "kernel": "6.8.0",
        "architecture": "x86_64",
        "runtime_environment": "host",
        "boot_time": NOW,
        "uptime_seconds": 3600.0,
    }
    return SystemInfo(**{**data, **overrides})


def make_process(pid: int, cpu: float, rss: int, name: str = "proc") -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name=f"{name}{pid}",
        username="root",
        status="sleeping",
        cpu_percent=cpu,
        memory_percent=round(rss / 1_000_000, 2),
        memory_rss_bytes=rss,
    )


def make_snapshot(process_count: int = 5) -> MetricsSnapshot:
    """A snapshot whose process lists hold ``process_count`` entries, best first."""
    procs = [
        make_process(pid, cpu=50.0 - pid, rss=(100 - pid) * 1_000)
        for pid in range(1, process_count + 1)
    ]
    return MetricsSnapshot(
        collected_at=NOW,
        system=make_system_info(),
        cpu=CpuMetrics(
            utilization_percent=12.5,
            load_avg_1m=0.5,
            load_avg_5m=0.4,
            load_avg_15m=0.3,
            logical_cores=8,
            physical_cores=4,
        ),
        memory=MemoryMetrics(
            ram_total_bytes=8_000,
            ram_used_bytes=3_000,
            ram_available_bytes=5_000,
            ram_percent=37.5,
            swap_total_bytes=1_000,
            swap_used_bytes=0,
            swap_percent=0.0,
        ),
        disks=[
            DiskUsage(
                device="/dev/sda1",
                mountpoint="/",
                fstype="ext4",
                total_bytes=1_000,
                used_bytes=400,
                free_bytes=600,
                percent=40.0,
            )
        ],
        network=NetworkMetrics(
            bytes_sent_total=10,
            bytes_recv_total=20,
            send_rate_bytes_per_sec=1.5,
            recv_rate_bytes_per_sec=2.5,
            interfaces=[
                NetworkInterface(
                    name="eth0",
                    is_up=True,
                    ipv4_addresses=["10.0.0.5"],
                    bytes_sent=10,
                    bytes_recv=20,
                )
            ],
        ),
        processes=ProcessMetrics(
            total_count=120, running_count=2, top_by_cpu=procs, top_by_memory=procs
        ),
    )


class FakeLiveMetrics:
    """Stand-in for LiveMetricsService: returns canned data or raises a canned error."""

    def __init__(self, snapshot: MetricsSnapshot | None = None, error: Exception | None = None):
        self.snapshot = snapshot or make_snapshot()
        self.error = error

    def get_snapshot(self) -> MetricsSnapshot:
        if self.error:
            raise self.error
        return self.snapshot

    def get_system_info(self) -> SystemInfo:
        if self.error:
            raise self.error
        return self.snapshot.system
