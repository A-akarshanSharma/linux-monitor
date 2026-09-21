"""Network counters, per-interface details and throughput rates."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

from app.models import NetworkInterface, NetworkMetrics

_LOOPBACK = "lo"


@dataclass(frozen=True)
class _Sample:
    taken_at: float
    bytes_sent: int
    bytes_recv: int


class NetworkCollector:
    """Collects network metrics and derives bytes/second rates.

    The kernel only exposes cumulative byte counters, which are meaningless on
    a graph. This class remembers the previous sample and computes the rate
    between polls, so it is stateful: keep one instance for the process lifetime.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._previous: _Sample | None = None

    def collect(self) -> NetworkMetrics:
        per_nic = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()

        interfaces: list[NetworkInterface] = []
        for name in sorted(stats):
            io = per_nic.get(name)
            interfaces.append(
                NetworkInterface(
                    name=name,
                    is_up=stats[name].isup,
                    speed_mbps=stats[name].speed or None,  # 0 means "unknown"
                    mtu=stats[name].mtu or None,
                    ipv4_addresses=[
                        a.address for a in addresses.get(name, []) if a.family == socket.AF_INET
                    ],
                    bytes_sent=io.bytes_sent if io else 0,
                    bytes_recv=io.bytes_recv if io else 0,
                )
            )

        # Loopback traffic is not "network traffic" for dashboard purposes.
        sent_total = sum(i.bytes_sent for i in interfaces if i.name != _LOOPBACK)
        recv_total = sum(i.bytes_recv for i in interfaces if i.name != _LOOPBACK)

        send_rate, recv_rate = self._compute_rates(sent_total, recv_total)
        return NetworkMetrics(
            bytes_sent_total=sent_total,
            bytes_recv_total=recv_total,
            send_rate_bytes_per_sec=send_rate,
            recv_rate_bytes_per_sec=recv_rate,
            interfaces=interfaces,
        )

    def _compute_rates(self, sent: int, recv: int) -> tuple[float | None, float | None]:
        now = self._clock()
        previous = self._previous
        self._previous = _Sample(now, sent, recv)

        if previous is None:
            return None, None
        elapsed = now - previous.taken_at
        sent_delta = sent - previous.bytes_sent
        recv_delta = recv - previous.bytes_recv
        # Negative delta = counter reset (interface removed/reloaded); skip this sample.
        if elapsed <= 0 or sent_delta < 0 or recv_delta < 0:
            return None, None
        return sent_delta / elapsed, recv_delta / elapsed
