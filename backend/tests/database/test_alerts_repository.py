from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.orm import AlertRow
from app.database.repositories import AlertsRepository
from app.database.session import create_session_factory
from app.models import AlertSeverity, AlertState

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path: Path) -> AlertsRepository:
    factory = create_session_factory(tmp_path / "alerts.db")
    return AlertsRepository(factory)


def test_upsert_creates_a_new_alert(repository: AlertsRepository) -> None:
    result = repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.WARNING,
        value=91.0,
        threshold=90.0,
        message="Memory high",
        now=NOW,
    )

    assert result.is_new is True
    assert result.previous_severity is None
    assert result.new_severity is AlertSeverity.WARNING

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].id == result.alert_id
    assert active[0].state == AlertState.WARNING
    assert active[0].value == 91.0
    assert active[0].first_triggered_at == NOW
    assert active[0].resolved_at is None


def test_upsert_on_an_open_alert_updates_it_instead_of_creating_a_second_row(
    repository: AlertsRepository,
) -> None:
    repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.WARNING,
        value=91.0,
        threshold=90.0,
        message="m1",
        now=NOW,
    )
    later = NOW + timedelta(seconds=30)

    result = repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.CRITICAL,
        value=97.0,
        threshold=95.0,
        message="m2",
        now=later,
    )

    assert result.is_new is False
    assert result.previous_severity is AlertSeverity.WARNING
    assert result.new_severity is AlertSeverity.CRITICAL

    active = repository.get_active_alerts()
    assert len(active) == 1
    assert active[0].state == AlertState.CRITICAL
    assert active[0].value == 97.0
    assert active[0].first_triggered_at == NOW  # unchanged
    assert active[0].last_updated_at == later


def test_different_targets_for_the_same_rule_are_independent(repository: AlertsRepository) -> None:
    repository.upsert_open_alert(
        rule_key="disk",
        target="/",
        severity=AlertSeverity.WARNING,
        value=85.0,
        threshold=80.0,
        message="root full",
        now=NOW,
    )
    repository.upsert_open_alert(
        rule_key="disk",
        target="/data",
        severity=AlertSeverity.CRITICAL,
        value=95.0,
        threshold=90.0,
        message="data full",
        now=NOW,
    )

    active = repository.get_active_alerts()
    assert {a.target for a in active} == {"/", "/data"}


def test_resolve_open_alert_marks_it_resolved(repository: AlertsRepository) -> None:
    repository.upsert_open_alert(
        rule_key="cpu",
        target="",
        severity=AlertSeverity.WARNING,
        value=90.0,
        threshold=85.0,
        message="cpu high",
        now=NOW,
    )
    later = NOW + timedelta(minutes=5)

    result = repository.resolve_open_alert("cpu", "", later)

    assert result is not None
    assert result.severity is AlertSeverity.WARNING
    assert repository.get_active_alerts() == []
    resolved = repository.get_resolved_alerts_since(NOW - timedelta(days=1))
    assert len(resolved) == 1
    assert resolved[0].state == AlertState.RESOLVED
    assert resolved[0].resolved_at == later


def test_resolve_with_nothing_open_is_a_no_op(repository: AlertsRepository) -> None:
    assert repository.resolve_open_alert("cpu", "", NOW) is None


def test_resolving_reopens_a_fresh_alert_on_the_next_upsert(repository: AlertsRepository) -> None:
    """A resolved alert must not block a brand new one for the same rule/target."""
    repository.upsert_open_alert(
        rule_key="cpu",
        target="",
        severity=AlertSeverity.WARNING,
        value=90.0,
        threshold=85.0,
        message="first",
        now=NOW,
    )
    repository.resolve_open_alert("cpu", "", NOW + timedelta(minutes=1))

    result = repository.upsert_open_alert(
        rule_key="cpu",
        target="",
        severity=AlertSeverity.WARNING,
        value=88.0,
        threshold=85.0,
        message="second",
        now=NOW + timedelta(minutes=10),
    )

    assert result.is_new is True
    assert len(repository.get_active_alerts()) == 1


def test_partial_unique_index_prevents_two_open_alerts_for_the_same_key(
    repository: AlertsRepository, tmp_path: Path
) -> None:
    """Defence in depth: even bypassing upsert_open_alert and inserting directly,
    the database itself refuses a second open row for the same (rule_key, target)."""
    with repository._session_factory() as session:
        session.add(
            AlertRow(
                rule_key="cpu",
                target="",
                severity="WARNING",
                value=1,
                threshold=1,
                message="a",
                first_triggered_at=NOW,
                last_updated_at=NOW,
                resolved_at=None,
            )
        )
        session.commit()

        session.add(
            AlertRow(
                rule_key="cpu",
                target="",
                severity="WARNING",
                value=2,
                threshold=1,
                message="b",
                first_triggered_at=NOW,
                last_updated_at=NOW,
                resolved_at=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_get_active_alerts_are_not_filtered_by_age(repository: AlertsRepository) -> None:
    old = NOW - timedelta(days=30)
    repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.WARNING,
        value=91.0,
        threshold=90.0,
        message="old and still open",
        now=old,
    )

    assert len(repository.get_active_alerts()) == 1


def test_get_resolved_alerts_since_excludes_older_resolutions(repository: AlertsRepository) -> None:
    repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.WARNING,
        value=91.0,
        threshold=90.0,
        message="m",
        now=NOW,
    )
    repository.resolve_open_alert("memory", "", NOW + timedelta(minutes=10))

    # Resolved at NOW+10min: a window starting at NOW+60min is entirely after that,
    # so it's excluded; a window starting at NOW+5min includes it.
    assert repository.get_resolved_alerts_since(NOW + timedelta(minutes=60)) == []
    assert len(repository.get_resolved_alerts_since(NOW + timedelta(minutes=5))) == 1


def test_prune_resolved_older_than_only_deletes_resolved_rows(repository: AlertsRepository) -> None:
    repository.upsert_open_alert(
        rule_key="cpu",
        target="",
        severity=AlertSeverity.WARNING,
        value=90.0,
        threshold=85.0,
        message="still open",
        now=NOW,
    )
    repository.upsert_open_alert(
        rule_key="memory",
        target="",
        severity=AlertSeverity.WARNING,
        value=91.0,
        threshold=90.0,
        message="will resolve",
        now=NOW,
    )
    repository.resolve_open_alert("memory", "", NOW + timedelta(minutes=1))

    deleted = repository.prune_resolved_older_than(NOW + timedelta(days=1))

    assert deleted == 1
    assert len(repository.get_active_alerts()) == 1  # the still-open cpu alert survives


def test_prune_never_deletes_open_alerts_regardless_of_age(repository: AlertsRepository) -> None:
    repository.upsert_open_alert(
        rule_key="cpu",
        target="",
        severity=AlertSeverity.WARNING,
        value=90.0,
        threshold=85.0,
        message="ancient but open",
        now=NOW - timedelta(days=365),
    )

    deleted = repository.prune_resolved_older_than(NOW)

    assert deleted == 0
    assert len(repository.get_active_alerts()) == 1
