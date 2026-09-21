import pytest

from app.collectors import cpu


def _patch_psutil(monkeypatch: pytest.MonkeyPatch, percent: float) -> None:
    monkeypatch.setattr(cpu.psutil, "cpu_percent", lambda interval=None: percent)
    monkeypatch.setattr(cpu.psutil, "getloadavg", lambda: (0.5, 1.0, 1.5))
    monkeypatch.setattr(cpu.psutil, "cpu_count", lambda logical=True: 8 if logical else 4)


def test_collect_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_psutil(monkeypatch, 42.5)

    metrics = cpu.collect_cpu()

    assert metrics.utilization_percent == 42.5
    assert (metrics.load_avg_1m, metrics.load_avg_5m, metrics.load_avg_15m) == (0.5, 1.0, 1.5)
    assert metrics.logical_cores == 8
    assert metrics.physical_cores == 4


def test_utilization_is_clamped_to_valid_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_psutil(monkeypatch, 100.7)

    assert cpu.collect_cpu().utilization_percent == 100.0


def test_unknown_core_counts_are_handled(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_psutil(monkeypatch, 10.0)
    monkeypatch.setattr(cpu.psutil, "cpu_count", lambda logical=True: None)

    metrics = cpu.collect_cpu()

    assert metrics.logical_cores == 1
    assert metrics.physical_cores is None


def test_prime_starts_a_non_blocking_measurement_window(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float | None] = []
    monkeypatch.setattr(cpu.psutil, "cpu_percent", lambda interval=None: calls.append(interval))

    cpu.prime_cpu_counters()

    assert calls == [None]
