from types import SimpleNamespace

import pytest

from app.collectors import memory


def test_collect_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=8_000, used=3_000, available=5_000, percent=37.5),
    )
    monkeypatch.setattr(
        memory.psutil,
        "swap_memory",
        lambda: SimpleNamespace(total=2_000, used=500, percent=25.0),
    )

    metrics = memory.collect_memory()

    assert metrics.ram_total_bytes == 8_000
    assert metrics.ram_used_bytes == 3_000
    assert metrics.ram_available_bytes == 5_000
    assert metrics.ram_percent == 37.5
    assert metrics.swap_total_bytes == 2_000
    assert metrics.swap_percent == 25.0


def test_system_without_swap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=1_000, used=100, available=900, percent=10.0),
    )
    monkeypatch.setattr(
        memory.psutil, "swap_memory", lambda: SimpleNamespace(total=0, used=0, percent=0.0)
    )

    metrics = memory.collect_memory()

    assert metrics.swap_total_bytes == 0
    assert metrics.swap_percent == 0.0
