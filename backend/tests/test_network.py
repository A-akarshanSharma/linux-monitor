from collections import namedtuple

import pytest

from app.collectors import network
from app.collectors.network import NetworkCollector

IO = namedtuple("IO", "bytes_sent bytes_recv")
Stats = namedtuple("Stats", "isup duplex speed mtu")
Addr = namedtuple("Addr", "family address")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _patch(monkeypatch: pytest.MonkeyPatch, counters: dict[str, IO]) -> None:
    stats = {name: Stats(True, 2, 1000, 1500) for name in counters}
    addrs = {
        name: [Addr(network.socket.AF_INET, f"10.0.0.{i + 1}")] for i, name in enumerate(counters)
    }
    monkeypatch.setattr(network.psutil, "net_io_counters", lambda pernic=False: counters)
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: stats)
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: addrs)


def test_first_sample_has_no_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"eth0": IO(100, 200)})

    metrics = NetworkCollector(clock=FakeClock()).collect()

    assert metrics.send_rate_bytes_per_sec is None
    assert metrics.recv_rate_bytes_per_sec is None
    assert metrics.bytes_sent_total == 100
    assert metrics.bytes_recv_total == 200


def test_rates_are_computed_between_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    collector = NetworkCollector(clock=clock)

    _patch(monkeypatch, {"eth0": IO(1_000, 5_000)})
    collector.collect()

    clock.now += 10
    _patch(monkeypatch, {"eth0": IO(3_000, 5_500)})
    metrics = collector.collect()

    assert metrics.send_rate_bytes_per_sec == 200.0  # 2000 bytes / 10 s
    assert metrics.recv_rate_bytes_per_sec == 50.0  # 500 bytes / 10 s


def test_counter_reset_yields_no_rate_then_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    collector = NetworkCollector(clock=clock)

    _patch(monkeypatch, {"eth0": IO(9_000, 9_000)})
    collector.collect()

    clock.now += 5
    _patch(monkeypatch, {"eth0": IO(10, 10)})  # counters went backwards
    assert collector.collect().send_rate_bytes_per_sec is None

    clock.now += 5
    _patch(monkeypatch, {"eth0": IO(60, 110)})
    metrics = collector.collect()
    assert metrics.send_rate_bytes_per_sec == 10.0
    assert metrics.recv_rate_bytes_per_sec == 20.0


def test_loopback_is_excluded_from_totals_but_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"lo": IO(999_999, 999_999), "eth0": IO(10, 20), "wlan0": IO(1, 2)})

    metrics = NetworkCollector(clock=FakeClock()).collect()

    assert metrics.bytes_sent_total == 11
    assert metrics.bytes_recv_total == 22
    assert {i.name for i in metrics.interfaces} == {"lo", "eth0", "wlan0"}


def test_interface_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"eth0": IO(10, 20)})
    # speed 0 means "unknown" in psutil
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {"eth0": Stats(True, 2, 0, 1500)})

    iface = NetworkCollector(clock=FakeClock()).collect().interfaces[0]

    assert iface.name == "eth0"
    assert iface.is_up is True
    assert iface.speed_mbps is None
    assert iface.mtu == 1500
    assert iface.ipv4_addresses == ["10.0.0.1"]
    assert (iface.bytes_sent, iface.bytes_recv) == (10, 20)


def test_interface_without_counters_reports_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"eth0": IO(10, 20)})
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {"veth9": Stats(False, 0, 0, 1500)})
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {})

    iface = NetworkCollector(clock=FakeClock()).collect().interfaces[0]

    assert iface.name == "veth9"
    assert iface.bytes_sent == 0
    assert iface.ipv4_addresses == []
