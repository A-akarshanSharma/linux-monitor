from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database.repositories import MetricsRepository
from app.database.session import create_session_factory
from tests.factories import make_snapshot

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path: Path) -> MetricsRepository:
    factory = create_session_factory(tmp_path / "test.db")
    return MetricsRepository(factory)


def test_save_and_read_back_a_snapshot(repository: MetricsRepository) -> None:
    snapshot = make_snapshot()
    snapshot.collected_at = NOW

    repository.save_snapshot(snapshot)
    points = repository.get_history(NOW - timedelta(minutes=1))

    assert len(points) == 1
    point = points[0]
    assert point.collected_at == NOW
    assert point.cpu_percent == snapshot.cpu.utilization_percent
    assert point.ram_percent == snapshot.memory.ram_percent
    assert point.ram_used_bytes == snapshot.memory.ram_used_bytes
    assert point.bytes_sent_total == snapshot.network.bytes_sent_total
    assert point.send_rate_bytes_per_sec == snapshot.network.send_rate_bytes_per_sec
    assert point.process_count == snapshot.processes.total_count


def test_collected_at_round_trips_as_utc(repository: MetricsRepository) -> None:
    """SQLite drops tzinfo on round trip; the repository must restore it as UTC."""
    snapshot = make_snapshot()
    snapshot.collected_at = NOW
    repository.save_snapshot(snapshot)

    point = repository.get_history(NOW - timedelta(minutes=1))[0]

    assert point.collected_at.tzinfo is not None
    assert point.collected_at == NOW


def test_null_network_rates_are_preserved(repository: MetricsRepository) -> None:
    snapshot = make_snapshot()
    snapshot.collected_at = NOW
    snapshot.network.send_rate_bytes_per_sec = None
    snapshot.network.recv_rate_bytes_per_sec = None

    repository.save_snapshot(snapshot)
    point = repository.get_history(NOW - timedelta(minutes=1))[0]

    assert point.send_rate_bytes_per_sec is None
    assert point.recv_rate_bytes_per_sec is None


def test_history_is_ordered_oldest_first(repository: MetricsRepository) -> None:
    for minutes_ago in [5, 20, 1, 10]:
        snapshot = make_snapshot()
        snapshot.collected_at = NOW - timedelta(minutes=minutes_ago)
        repository.save_snapshot(snapshot)

    points = repository.get_history(NOW - timedelta(minutes=30))

    assert [p.collected_at for p in points] == [
        NOW - timedelta(minutes=20),
        NOW - timedelta(minutes=10),
        NOW - timedelta(minutes=5),
        NOW - timedelta(minutes=1),
    ]


def test_since_filter_excludes_older_samples(repository: MetricsRepository) -> None:
    for minutes_ago in [5, 90]:
        snapshot = make_snapshot()
        snapshot.collected_at = NOW - timedelta(minutes=minutes_ago)
        repository.save_snapshot(snapshot)

    points = repository.get_history(NOW - timedelta(minutes=60))

    assert len(points) == 1
    assert points[0].collected_at == NOW - timedelta(minutes=5)


def test_since_boundary_is_inclusive(repository: MetricsRepository) -> None:
    snapshot = make_snapshot()
    snapshot.collected_at = NOW - timedelta(minutes=60)
    repository.save_snapshot(snapshot)

    assert len(repository.get_history(NOW - timedelta(minutes=60))) == 1


def test_no_samples_returns_empty_list(repository: MetricsRepository) -> None:
    assert repository.get_history(NOW - timedelta(minutes=60)) == []


def test_prune_older_than_deletes_only_old_rows_and_reports_count(
    repository: MetricsRepository,
) -> None:
    for minutes_ago in [5, 60, 120, 200]:
        snapshot = make_snapshot()
        snapshot.collected_at = NOW - timedelta(minutes=minutes_ago)
        repository.save_snapshot(snapshot)

    deleted = repository.prune_older_than(NOW - timedelta(minutes=100))

    assert deleted == 2  # the 120 and 200 minute-old rows
    remaining = repository.get_history(NOW - timedelta(days=1))
    assert [p.collected_at for p in remaining] == [
        NOW - timedelta(minutes=60),
        NOW - timedelta(minutes=5),
    ]


def test_prune_with_nothing_to_delete_returns_zero(repository: MetricsRepository) -> None:
    snapshot = make_snapshot()
    snapshot.collected_at = NOW
    repository.save_snapshot(snapshot)

    assert repository.prune_older_than(NOW - timedelta(days=7)) == 0


def test_count_reflects_stored_rows(repository: MetricsRepository) -> None:
    assert repository.count() == 0

    for _ in range(3):
        snapshot = make_snapshot()
        snapshot.collected_at = NOW
        repository.save_snapshot(snapshot)

    assert repository.count() == 3
