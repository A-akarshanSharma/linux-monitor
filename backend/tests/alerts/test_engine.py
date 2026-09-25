import copy
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.alerts.engine import AlertEngine
from app.database.repositories import AlertsRepository
from app.database.session import create_session_factory
from app.models import AlertState
from tests.factories import make_snapshot

FIXED_START = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: datetime = FIXED_START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def repository(tmp_path: Path) -> AlertsRepository:
    factory = create_session_factory(tmp_path / "engine.db")
    return AlertsRepository(factory)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def engine(repository: AlertsRepository, settings, clock: FakeClock) -> AlertEngine:
    return AlertEngine(repository, settings, clock=clock)


# ---- memory: no sustained-duration requirement, fires on the first breaching cycle ----


def test_memory_alert_fires_on_first_breaching_cycle(engine, repository, settings, caplog) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent

    with caplog.at_level(logging.INFO):
        engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].rule_key == "memory"
    assert active[0].state == AlertState.WARNING
    assert any(r.message == "alert_created" for r in caplog.records)


def test_value_just_below_warning_never_alerts(engine, repository, settings) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent - 0.1

    engine.evaluate(snapshot)

    assert repository.get_active_alerts() == []


def test_repeated_breach_does_not_create_duplicate_rows(engine, repository, settings) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent

    engine.evaluate(snapshot)
    engine.evaluate(snapshot)
    engine.evaluate(snapshot)

    assert len(repository.get_active_alerts()) == 1


def test_alert_escalates_to_critical_on_the_same_row(engine, repository, settings, caplog) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent
    engine.evaluate(snapshot)
    first_id = repository.get_active_alerts()[0].id

    snapshot.memory.ram_percent = settings.memory_critical_percent
    with caplog.at_level(logging.INFO):
        engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].id == first_id
    assert active[0].state == AlertState.CRITICAL
    assert any(r.message == "alert_severity_changed" for r in caplog.records)


def test_alert_deescalates_without_creating_a_new_row(engine, repository, settings) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_critical_percent
    engine.evaluate(snapshot)
    row_id = repository.get_active_alerts()[0].id

    snapshot.memory.ram_percent = settings.memory_warning_percent  # still breaching warning
    engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].id == row_id
    assert active[0].state == AlertState.WARNING


def test_alert_resolves_when_back_to_normal(engine, repository, settings, caplog) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = settings.memory_warning_percent
    engine.evaluate(snapshot)
    assert len(repository.get_active_alerts()) == 1

    snapshot.memory.ram_percent = settings.memory_warning_percent - 10
    with caplog.at_level(logging.INFO):
        engine.evaluate(snapshot)

    assert repository.get_active_alerts() == []
    resolved = repository.get_resolved_alerts_since(FIXED_START - timedelta(days=1))
    assert len(resolved) == 1
    assert resolved[0].state == AlertState.RESOLVED
    assert any(r.message == "alert_resolved" for r in caplog.records)


def test_steady_normal_state_never_logs_anything(engine, repository, settings, caplog) -> None:
    snapshot = make_snapshot()
    snapshot.memory.ram_percent = 10.0  # nowhere near warning

    with caplog.at_level(logging.INFO):
        engine.evaluate(snapshot)
        engine.evaluate(snapshot)

    assert repository.get_active_alerts() == []
    assert caplog.records == []


# ---- cpu: sustained-duration requirement ----


def test_cpu_does_not_alert_before_sustained_duration_elapses(
    engine, repository, settings, clock
) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent

    engine.evaluate(snapshot)
    assert repository.get_active_alerts() == []

    clock.advance(settings.cpu_sustained_seconds - 1)
    engine.evaluate(snapshot)
    assert repository.get_active_alerts() == []  # still short


def test_cpu_alerts_once_sustained_duration_elapses(engine, repository, settings, clock) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent
    engine.evaluate(snapshot)

    clock.advance(settings.cpu_sustained_seconds)
    engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].rule_key == "cpu"


def test_cpu_breach_timer_resets_after_a_dip_below_threshold(
    engine, repository, settings, clock
) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent
    engine.evaluate(snapshot)
    clock.advance(settings.cpu_sustained_seconds - 5)
    engine.evaluate(snapshot)

    snapshot.cpu.utilization_percent = settings.cpu_warning_percent - 20  # dips below
    engine.evaluate(snapshot)

    snapshot.cpu.utilization_percent = settings.cpu_warning_percent  # breaches again
    clock.advance(settings.cpu_sustained_seconds - 1)
    engine.evaluate(snapshot)

    assert repository.get_active_alerts() == []  # timer restarted, not held long enough yet


def test_cpu_can_still_escalate_to_critical_immediately_once_open(
    engine, repository, settings, clock
) -> None:
    snapshot = make_snapshot()
    snapshot.cpu.utilization_percent = settings.cpu_warning_percent
    engine.evaluate(snapshot)
    clock.advance(settings.cpu_sustained_seconds)
    engine.evaluate(snapshot)  # alert now open as WARNING

    snapshot.cpu.utilization_percent = settings.cpu_critical_percent
    engine.evaluate(snapshot)  # no additional wait required to escalate

    assert repository.get_active_alerts()[0].state == AlertState.CRITICAL


# ---- disk: evaluated per mount point, independently ----


def test_disk_alerts_are_tracked_independently_per_mountpoint(engine, repository, settings) -> None:
    snapshot = make_snapshot()
    extra_disk = copy.deepcopy(snapshot.disks[0])
    extra_disk.mountpoint = "/data"
    extra_disk.percent = settings.disk_warning_percent
    snapshot.disks.append(extra_disk)
    snapshot.disks[0].percent = settings.disk_warning_percent

    engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert {a.target for a in active} == {"/", "/data"}


def test_resolving_one_disk_does_not_affect_another(engine, repository, settings) -> None:
    snapshot = make_snapshot()
    extra_disk = copy.deepcopy(snapshot.disks[0])
    extra_disk.mountpoint = "/data"
    extra_disk.percent = settings.disk_warning_percent
    snapshot.disks.append(extra_disk)
    snapshot.disks[0].percent = settings.disk_warning_percent
    engine.evaluate(snapshot)

    snapshot.disks[0].percent = 10.0  # "/" back to normal; "/data" still breaching
    engine.evaluate(snapshot)

    active = repository.get_active_alerts()
    assert {a.target for a in active} == {"/data"}


# ---- service: binary, no duration ----


def test_service_down_fires_critical_immediately(engine, repository) -> None:
    engine.evaluate(make_snapshot(), service_states={"nginx": False, "ssh": True})

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].rule_key == "service"
    assert active[0].target == "nginx"
    assert active[0].state == AlertState.CRITICAL


def test_service_back_up_resolves_its_alert(engine, repository) -> None:
    engine.evaluate(make_snapshot(), service_states={"nginx": False})
    assert len(repository.get_active_alerts()) == 1

    engine.evaluate(make_snapshot(), service_states={"nginx": True})

    assert repository.get_active_alerts() == []


def test_no_services_configured_is_fine(engine, repository) -> None:
    """The default call in Phase 4 (no service monitoring wired in yet): must not error."""
    engine.evaluate(make_snapshot())

    assert repository.get_active_alerts() == []
