import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import CollectionError
from app.services.scheduler import MetricsScheduler
from tests.factories import make_snapshot

FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeCollector:
    def __init__(self) -> None:
        self.primed = 0
        self.collect_calls = 0
        self.error: Exception | None = None

    def prime(self) -> None:
        self.primed += 1

    def collect(self):
        self.collect_calls += 1
        if self.error:
            raise self.error
        return make_snapshot()


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[object] = []
        self.prune_calls: list[datetime] = []
        self.save_error: Exception | None = None

    def save_snapshot(self, snapshot) -> None:
        if self.save_error:
            raise self.save_error
        self.saved.append(snapshot)

    def prune_older_than(self, cutoff: datetime) -> int:
        self.prune_calls.append(cutoff)
        return 0


@pytest.fixture
def collector() -> FakeCollector:
    return FakeCollector()


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


def make_scheduler(collector, repository, settings, **kwargs) -> MetricsScheduler:
    return MetricsScheduler(collector, repository, settings, **kwargs)


class FakeAlertEngine:
    def __init__(self) -> None:
        self.evaluate_calls: list[object] = []
        self.error: Exception | None = None

    def evaluate(self, snapshot, service_states=None) -> None:
        self.evaluate_calls.append(snapshot)
        if self.error:
            raise self.error


class FakeAlertsRepository:
    def __init__(self) -> None:
        self.prune_calls: list[datetime] = []

    def prune_resolved_older_than(self, cutoff: datetime) -> int:
        self.prune_calls.append(cutoff)
        return 0


def test_collect_once_invokes_the_alert_engine_when_provided(
    collector, repository, settings
) -> None:
    alert_engine = FakeAlertEngine()
    scheduler = make_scheduler(collector, repository, settings, alert_engine=alert_engine)

    scheduler._collect_once()

    assert len(alert_engine.evaluate_calls) == 1


def test_no_alert_engine_provided_is_fine(collector, repository, settings) -> None:
    scheduler = make_scheduler(collector, repository, settings)  # alert_engine defaults to None

    scheduler._collect_once()  # must not raise

    assert scheduler.get_latest() is not None


def test_alert_engine_failure_does_not_break_metric_collection(
    collector, repository, settings, caplog: pytest.LogCaptureFixture
) -> None:
    alert_engine = FakeAlertEngine()
    alert_engine.error = RuntimeError("bad rule")
    scheduler = make_scheduler(collector, repository, settings, alert_engine=alert_engine)

    with caplog.at_level(logging.ERROR):
        scheduler._collect_once()  # must not raise

    assert scheduler.get_latest() is not None
    assert any(r.message == "alert_evaluation_failed" for r in caplog.records)


def test_alerts_repository_is_pruned_using_configured_retention(
    collector, repository, settings
) -> None:
    settings = settings.model_copy(update={"retention_days": 3})
    alerts_repository = FakeAlertsRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        alerts_repository=alerts_repository,
        clock=lambda: FIXED_NOW,
    )

    scheduler._collect_once()

    assert alerts_repository.prune_calls == [FIXED_NOW - timedelta(days=3)]


def test_alerts_prune_failure_does_not_break_metric_collection(
    collector, repository, settings, caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenAlertsRepository:
        def prune_resolved_older_than(self, cutoff: datetime) -> int:
            raise RuntimeError("db locked")

    scheduler = make_scheduler(
        collector, repository, settings, alerts_repository=BrokenAlertsRepository()
    )

    with caplog.at_level(logging.ERROR):
        scheduler._collect_once()  # must not raise

    assert scheduler.get_latest() is not None
    assert any(r.message == "alerts_prune_failed" for r in caplog.records)


# ---- _collect_once (called directly; no real threading, no timing dependency) ----


def test_collect_once_stores_latest_and_persists(collector, repository, settings) -> None:
    scheduler = make_scheduler(collector, repository, settings, clock=lambda: FIXED_NOW)

    scheduler._collect_once()

    assert scheduler.get_latest() is not None
    assert len(repository.saved) == 1


def test_collect_once_prunes_using_configured_retention(collector, repository, settings) -> None:
    settings = settings.model_copy(update={"retention_days": 3})
    scheduler = make_scheduler(collector, repository, settings, clock=lambda: FIXED_NOW)

    scheduler._collect_once()

    assert repository.prune_calls == [FIXED_NOW - timedelta(days=3)]


def test_collection_failure_is_not_fatal_and_leaves_latest_unchanged(
    collector, repository, settings
) -> None:
    scheduler = make_scheduler(collector, repository, settings, clock=lambda: FIXED_NOW)
    scheduler._collect_once()  # succeeds once
    first_latest = scheduler.get_latest()

    collector.error = CollectionError("cpu", OSError("boom"))
    scheduler._collect_once()  # fails

    assert scheduler.get_latest() is first_latest
    assert len(repository.saved) == 1  # the failed cycle never reached save_snapshot


def test_persistence_failure_does_not_prevent_latest_from_updating(
    collector, repository, settings
) -> None:
    scheduler = make_scheduler(collector, repository, settings, clock=lambda: FIXED_NOW)
    repository.save_error = RuntimeError("disk full")

    scheduler._collect_once()  # must not raise

    assert scheduler.get_latest() is not None
    assert repository.saved == []


def test_get_latest_raises_before_any_successful_collection(
    collector, repository, settings
) -> None:
    scheduler = make_scheduler(collector, repository, settings)

    with pytest.raises(CollectionError) as exc_info:
        scheduler.get_latest()
    assert exc_info.value.collector == "scheduler"


# ---- start()/stop() lifecycle (real thread, tiny real interval) ----


def test_start_primes_and_collects_once_synchronously(collector, repository, settings) -> None:
    settings = settings.model_copy(update={"polling_interval_seconds": 60})
    scheduler = make_scheduler(collector, repository, settings)

    scheduler.start()
    try:
        assert collector.primed == 1
        assert collector.collect_calls == 1
        assert scheduler.get_latest() is not None  # available immediately, no waiting for start()
    finally:
        scheduler.stop()


def test_background_thread_collects_on_the_configured_interval(
    collector, repository, settings
) -> None:
    settings = settings.model_copy(update={"polling_interval_seconds": 1})
    scheduler = make_scheduler(collector, repository, settings)

    scheduler.start()
    try:
        assert collector.collect_calls == 1  # the synchronous first collection
        time.sleep(2.3)
        assert collector.collect_calls >= 3  # ~2 more cycles at 1s
    finally:
        scheduler.stop()


def test_stop_halts_the_background_thread_promptly(collector, repository, settings) -> None:
    settings = settings.model_copy(update={"polling_interval_seconds": 1})
    scheduler = make_scheduler(collector, repository, settings)
    scheduler.start()

    stop_started = time.monotonic()
    scheduler.stop()
    stop_duration = time.monotonic() - stop_started

    assert stop_duration < 0.5  # interrupted immediately, not waiting out the interval
    calls_at_stop = collector.collect_calls
    time.sleep(1.3)
    assert collector.collect_calls == calls_at_stop  # nothing collected after stop()
