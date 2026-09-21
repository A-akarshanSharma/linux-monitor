"""Snapshot aggregation, including one real (unmocked) smoke test against this machine."""

import json

import pytest

from app.collectors import CollectionError, SnapshotCollector, snapshot
from app.config import Settings
from app.models import MetricsSnapshot


def test_real_snapshot_smoke(settings: Settings) -> None:
    collector = SnapshotCollector(settings)
    collector.prime()

    result = collector.collect()

    assert result.system.hostname
    assert 0 <= result.cpu.utilization_percent <= 100
    assert result.cpu.logical_cores >= 1
    assert result.memory.ram_total_bytes > 0
    assert 0 <= result.memory.ram_percent <= 100
    assert result.processes.total_count > 0
    assert len(result.processes.top_by_cpu) <= settings.top_processes_count
    assert result.collected_at.tzinfo is not None


def test_snapshot_survives_json_round_trip(settings: Settings) -> None:
    collector = SnapshotCollector(settings)
    collector.prime()
    original = collector.collect()

    restored = MetricsSnapshot.model_validate_json(original.model_dump_json())

    assert restored == original
    assert json.loads(original.model_dump_json())["cpu"]["logical_cores"] >= 1


def test_second_snapshot_has_network_rates(settings: Settings) -> None:
    collector = SnapshotCollector(settings)
    collector.prime()  # takes the baseline network sample

    result = collector.collect()

    assert result.network.send_rate_bytes_per_sec is not None
    assert result.network.recv_rate_bytes_per_sec is not None


def test_collector_failure_is_wrapped_with_collector_name(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    def broken() -> None:
        raise RuntimeError("cannot read /proc/meminfo")

    monkeypatch.setattr(snapshot, "collect_memory", broken)
    collector = SnapshotCollector(settings)

    with pytest.raises(CollectionError) as exc_info:
        collector.collect()

    assert exc_info.value.collector == "memory"
    assert "cannot read /proc/meminfo" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_top_processes_override_limits_list_size(settings: Settings) -> None:
    collector = SnapshotCollector(settings)
    collector.prime()

    result = collector.collect(top_processes=1)

    assert len(result.processes.top_by_cpu) == 1
    assert len(result.processes.top_by_memory) == 1
