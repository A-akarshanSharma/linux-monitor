from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database.repositories import ServicesRepository
from app.database.session import create_session_factory
from app.models import ServiceState

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path: Path) -> ServicesRepository:
    factory = create_session_factory(tmp_path / "services.db")
    return ServicesRepository(factory)


def test_upsert_creates_a_new_row(repository: ServicesRepository) -> None:
    result = repository.upsert_status(
        name="nginx", state=ServiceState.RUNNING, detail="active", now=NOW
    )

    assert result.changed is True
    assert result.previous_state is None
    assert result.new_state is ServiceState.RUNNING

    statuses = repository.get_all_statuses()
    assert len(statuses) == 1
    assert statuses[0].name == "nginx"
    assert statuses[0].state is ServiceState.RUNNING
    assert statuses[0].last_checked_at == NOW
    assert statuses[0].last_changed_at == NOW


def test_upsert_with_same_state_updates_checked_at_but_not_changed_at(
    repository: ServicesRepository,
) -> None:
    repository.upsert_status(name="nginx", state=ServiceState.RUNNING, detail="active", now=NOW)
    later = NOW + timedelta(minutes=10)

    result = repository.upsert_status(
        name="nginx", state=ServiceState.RUNNING, detail="active", now=later
    )

    assert result.changed is False
    status = repository.get_all_statuses()[0]
    assert status.last_checked_at == later
    assert status.last_changed_at == NOW  # unchanged: state never actually differed


def test_upsert_with_a_different_state_updates_both_timestamps(
    repository: ServicesRepository,
) -> None:
    repository.upsert_status(name="nginx", state=ServiceState.RUNNING, detail="active", now=NOW)
    later = NOW + timedelta(minutes=10)

    result = repository.upsert_status(
        name="nginx", state=ServiceState.STOPPED, detail="inactive", now=later
    )

    assert result.changed is True
    assert result.previous_state is ServiceState.RUNNING
    assert result.new_state is ServiceState.STOPPED
    status = repository.get_all_statuses()[0]
    assert status.state is ServiceState.STOPPED
    assert status.detail == "inactive"
    assert status.last_checked_at == later
    assert status.last_changed_at == later


def test_different_services_are_independent(repository: ServicesRepository) -> None:
    repository.upsert_status(name="nginx", state=ServiceState.RUNNING, detail=None, now=NOW)
    repository.upsert_status(name="ssh", state=ServiceState.STOPPED, detail=None, now=NOW)

    statuses = {s.name: s.state for s in repository.get_all_statuses()}
    assert statuses == {"nginx": ServiceState.RUNNING, "ssh": ServiceState.STOPPED}


def test_get_all_statuses_preserves_first_check_order(repository: ServicesRepository) -> None:
    for name in ["docker", "nginx", "ssh"]:  # deliberately not alphabetical
        repository.upsert_status(name=name, state=ServiceState.RUNNING, detail=None, now=NOW)

    names = [s.name for s in repository.get_all_statuses()]

    assert names == ["docker", "nginx", "ssh"]


def test_no_services_checked_yet_returns_empty_list(repository: ServicesRepository) -> None:
    assert repository.get_all_statuses() == []


def test_detail_can_be_none(repository: ServicesRepository) -> None:
    repository.upsert_status(name="nginx", state=ServiceState.RUNNING, detail=None, now=NOW)

    assert repository.get_all_statuses()[0].detail is None


def test_timestamps_round_trip_as_utc(repository: ServicesRepository) -> None:
    """Same SQLite tz-dropping quirk as metrics/alerts - must be restored as UTC."""
    repository.upsert_status(name="nginx", state=ServiceState.RUNNING, detail=None, now=NOW)

    status = repository.get_all_statuses()[0]

    assert status.last_checked_at.tzinfo is not None
    assert status.last_checked_at == NOW
