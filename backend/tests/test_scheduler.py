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
        self.evaluate_service_states: list[dict] = []
        self.error: Exception | None = None

    def evaluate(self, snapshot, service_states=None) -> None:
        self.evaluate_calls.append(snapshot)
        self.evaluate_service_states.append(service_states)
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


# ---- service checking wiring ----


class FakeServicesRepository:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def upsert_status(self, *, name, state, detail, now):
        from app.database.repositories import ServiceUpsertResult

        self.upserts.append({"name": name, "state": state, "detail": detail, "now": now})
        return ServiceUpsertResult(changed=True, previous_state=None, new_state=state)


def test_no_services_repository_configured_skips_service_checks(
    collector, repository, settings
) -> None:
    alert_engine = FakeAlertEngine()
    scheduler = make_scheduler(collector, repository, settings, alert_engine=alert_engine)

    scheduler._collect_once()  # must not raise; no services_repository, no monitored names

    assert alert_engine.evaluate_service_states == [{}]


def test_no_monitored_service_names_skips_service_checks(collector, repository, settings) -> None:
    services_repository = FakeServicesRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        services_repository=services_repository,
        monitored_service_names=[],
    )

    scheduler._collect_once()

    assert services_repository.upserts == []


def test_services_are_checked_even_without_an_alert_engine(collector, repository, settings) -> None:
    """Regression test: /api/services must work whether or not alerting is
    configured, so service checking must not be nested inside the alert-engine
    branch."""
    services_repository = FakeServicesRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        alert_engine=None,
        services_repository=services_repository,
        monitored_service_names=["nginx"],
    )

    scheduler._collect_once()

    assert len(services_repository.upserts) == 1
    assert services_repository.upserts[0]["name"] == "nginx"


def test_configured_services_are_checked_and_persisted(collector, repository, settings) -> None:
    from app.models import ServiceState
    from app.services.service_monitor import ServiceCheck

    def fake_check_services(names, **kwargs):
        now = datetime.now(timezone.utc)
        return [ServiceCheck(name, ServiceState.RUNNING, "active", now) for name in names]

    services_repository = FakeServicesRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        services_repository=services_repository,
        monitored_service_names=["nginx", "ssh"],
    )

    import app.services.scheduler as scheduler_module

    original = scheduler_module.check_services
    scheduler_module.check_services = fake_check_services
    try:
        scheduler._collect_once()
    finally:
        scheduler_module.check_services = original

    assert {u["name"] for u in services_repository.upserts} == {"nginx", "ssh"}


def test_alert_engine_receives_service_states_excluding_unknown(
    collector, repository, settings
) -> None:
    from app.models import ServiceState
    from app.services.service_monitor import ServiceCheck

    def fake_check_services(names, **kwargs):
        now = datetime.now(timezone.utc)
        return [
            ServiceCheck("nginx", ServiceState.RUNNING, "active", now),
            ServiceCheck("ssh", ServiceState.STOPPED, "inactive", now),
            ServiceCheck("docker", ServiceState.UNKNOWN, "no systemd", now),
        ]

    alert_engine = FakeAlertEngine()
    services_repository = FakeServicesRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        alert_engine=alert_engine,
        services_repository=services_repository,
        monitored_service_names=["nginx", "ssh", "docker"],
    )

    import app.services.scheduler as scheduler_module

    original = scheduler_module.check_services
    scheduler_module.check_services = fake_check_services
    try:
        scheduler._collect_once()
    finally:
        scheduler_module.check_services = original

    passed_service_states = alert_engine.evaluate_service_states[-1]
    assert passed_service_states == {"nginx": True, "ssh": False}  # docker (UNKNOWN) excluded


def test_service_check_failure_does_not_break_metric_collection(
    collector, repository, settings, caplog: pytest.LogCaptureFixture
) -> None:
    services_repository = FakeServicesRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        services_repository=services_repository,
        monitored_service_names=["nginx"],
    )

    import app.services.scheduler as scheduler_module

    def broken_check_services(names, **kwargs):
        raise RuntimeError("subprocess exploded")

    original = scheduler_module.check_services
    scheduler_module.check_services = broken_check_services
    try:
        with caplog.at_level(logging.ERROR):
            scheduler._collect_once()  # must not raise
    finally:
        scheduler_module.check_services = original

    assert scheduler.get_latest() is not None
    assert any(r.message == "service_check_failed" for r in caplog.records)


def test_service_persist_failure_for_one_service_does_not_block_others(
    collector, repository, settings, caplog: pytest.LogCaptureFixture
) -> None:
    from app.models import ServiceState
    from app.services.service_monitor import ServiceCheck

    class PartiallyBrokenRepository:
        def __init__(self) -> None:
            self.succeeded: list[str] = []

        def upsert_status(self, *, name, state, detail, now):
            from app.database.repositories import ServiceUpsertResult

            if name == "ssh":
                raise RuntimeError("db locked")
            self.succeeded.append(name)
            return ServiceUpsertResult(changed=True, previous_state=None, new_state=state)

    def fake_check_services(names, **kwargs):
        now = datetime.now(timezone.utc)
        return [ServiceCheck(name, ServiceState.RUNNING, "active", now) for name in names]

    repo = PartiallyBrokenRepository()
    scheduler = make_scheduler(
        collector,
        repository,
        settings,
        services_repository=repo,
        monitored_service_names=["nginx", "ssh", "docker"],
    )

    import app.services.scheduler as scheduler_module

    original = scheduler_module.check_services
    scheduler_module.check_services = fake_check_services
    try:
        with caplog.at_level(logging.ERROR):
            scheduler._collect_once()  # must not raise
    finally:
        scheduler_module.check_services = original

    assert repo.succeeded == ["nginx", "docker"]
    assert any(r.message == "service_status_persist_failed" for r in caplog.records)
