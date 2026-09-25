"""Pydantic models describing collected metrics.

These are the shared vocabulary of the application: collectors produce them,
the database layer persists them, and the API serialises them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RuntimeEnvironment = Literal["host", "wsl", "container"]


class SystemInfo(BaseModel):
    hostname: str
    ip_address: str = Field(
        description="Primary IPv4 address (the one used for the default route)."
    )
    os_name: str = Field(description="Distribution name, e.g. 'Ubuntu 24.04.1 LTS'.")
    kernel: str
    architecture: str
    runtime_environment: RuntimeEnvironment = Field(
        description="Where the agent is running. Metrics from 'wsl' and 'container' describe "
        "the VM / container view, not necessarily the physical machine."
    )
    boot_time: datetime
    uptime_seconds: float = Field(ge=0)


class CpuMetrics(BaseModel):
    utilization_percent: float = Field(ge=0, le=100)
    load_avg_1m: float = Field(ge=0)
    load_avg_5m: float = Field(ge=0)
    load_avg_15m: float = Field(ge=0)
    logical_cores: int = Field(ge=1)
    physical_cores: int | None = None


class MemoryMetrics(BaseModel):
    ram_total_bytes: int = Field(ge=0)
    ram_used_bytes: int = Field(ge=0)
    ram_available_bytes: int = Field(ge=0)
    ram_percent: float = Field(ge=0, le=100, description="(total - available) / total * 100")
    swap_total_bytes: int = Field(ge=0)
    swap_used_bytes: int = Field(ge=0)
    swap_percent: float = Field(ge=0, le=100)


class DiskUsage(BaseModel):
    device: str
    mountpoint: str
    fstype: str
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class NetworkInterface(BaseModel):
    name: str
    is_up: bool
    speed_mbps: int | None = None
    mtu: int | None = None
    ipv4_addresses: list[str] = Field(default_factory=list)
    bytes_sent: int = Field(ge=0)
    bytes_recv: int = Field(ge=0)


class NetworkMetrics(BaseModel):
    bytes_sent_total: int = Field(ge=0, description="Cumulative, all non-loopback interfaces.")
    bytes_recv_total: int = Field(ge=0, description="Cumulative, all non-loopback interfaces.")
    send_rate_bytes_per_sec: float | None = Field(
        default=None, description="None until two samples exist or after a counter reset."
    )
    recv_rate_bytes_per_sec: float | None = None
    interfaces: list[NetworkInterface]


class ProcessInfo(BaseModel):
    pid: int
    name: str
    username: str | None = None
    status: str
    cpu_percent: float = Field(ge=0, description="Like `top`: 100 means one full core.")
    memory_percent: float = Field(ge=0, le=100)
    memory_rss_bytes: int = Field(ge=0)


class ProcessMetrics(BaseModel):
    total_count: int = Field(ge=0)
    running_count: int = Field(ge=0, description="Processes currently in the 'running' state.")
    top_by_cpu: list[ProcessInfo]
    top_by_memory: list[ProcessInfo]


class MetricHistoryPoint(BaseModel):
    """One stored sample, as returned by GET /api/metrics/history."""

    collected_at: datetime
    cpu_percent: float = Field(ge=0, le=100)
    load_avg_1m: float = Field(ge=0)
    ram_percent: float = Field(ge=0, le=100)
    ram_used_bytes: int = Field(ge=0)
    ram_total_bytes: int = Field(ge=0)
    swap_percent: float = Field(ge=0, le=100)
    bytes_sent_total: int = Field(ge=0)
    bytes_recv_total: int = Field(ge=0)
    send_rate_bytes_per_sec: float | None = None
    recv_rate_bytes_per_sec: float | None = None
    process_count: int = Field(ge=0)


class MetricsSnapshot(BaseModel):
    """Everything collected in one polling cycle."""

    collected_at: datetime
    system: SystemInfo
    cpu: CpuMetrics
    memory: MemoryMetrics
    disks: list[DiskUsage]
    network: NetworkMetrics
    processes: ProcessMetrics
