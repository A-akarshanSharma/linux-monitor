from datetime import datetime, timedelta, timezone

import pytest

from app.models import AlertState
from tests.factories import FakeAlertsRepository, make_alert_record

NOW = datetime.now(timezone.utc)


def test_returns_active_and_recently_resolved_combined(
    make_client, fake_service, fake_repository
) -> None:
    active = [make_alert_record(1, state=AlertState.WARNING, last_updated_at=NOW)]
    resolved = [
        make_alert_record(
            2,
            state=AlertState.RESOLVED,
            resolved_at=NOW - timedelta(minutes=5),
            last_updated_at=NOW - timedelta(minutes=5),
        )
    ]
    client = make_client(fake_service, fake_repository, FakeAlertsRepository(active, resolved))

    response = client.get("/api/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["active_count"] == 1
    assert body["count"] == 2
    assert {a["id"] for a in body["alerts"]} == {1, 2}


def test_active_alerts_are_included_regardless_of_the_minutes_window(
    make_client, fake_service, fake_repository
) -> None:
    old_active = [
        make_alert_record(
            3,
            state=AlertState.CRITICAL,
            first_triggered_at=NOW - timedelta(days=5),
            last_updated_at=NOW - timedelta(days=5),
        )
    ]
    client = make_client(fake_service, fake_repository, FakeAlertsRepository(old_active, []))

    body = client.get("/api/alerts", params={"minutes": 5}).json()

    assert body["active_count"] == 1


def test_resolved_outside_the_window_is_excluded(
    make_client, fake_service, fake_repository
) -> None:
    resolved = [
        make_alert_record(
            4,
            state=AlertState.RESOLVED,
            resolved_at=NOW - timedelta(hours=2),
            last_updated_at=NOW - timedelta(hours=2),
        )
    ]
    client = make_client(fake_service, fake_repository, FakeAlertsRepository([], resolved))

    body = client.get("/api/alerts", params={"minutes": 30}).json()

    assert body["count"] == 0


def test_default_minutes_comes_from_settings(
    make_client, fake_service, fake_repository, settings
) -> None:
    repository = FakeAlertsRepository([], [])
    client = make_client(fake_service, fake_repository, repository)

    client.get("/api/alerts")

    since = repository.resolved_since_calls[-1]
    expected = datetime.now(timezone.utc) - timedelta(
        minutes=settings.alerts_history_default_minutes
    )
    assert abs((since - expected).total_seconds()) < 2


def test_alerts_are_sorted_most_recently_updated_first(
    make_client, fake_service, fake_repository
) -> None:
    active = [
        make_alert_record(1, target="/", last_updated_at=NOW - timedelta(minutes=10)),
        make_alert_record(2, target="/data", last_updated_at=NOW),
    ]
    client = make_client(fake_service, fake_repository, FakeAlertsRepository(active, []))

    body = client.get("/api/alerts").json()

    assert [a["id"] for a in body["alerts"]] == [2, 1]


def test_no_alerts_returns_empty(make_client, fake_service, fake_repository) -> None:
    client = make_client(fake_service, fake_repository, FakeAlertsRepository([], []))

    response = client.get("/api/alerts")

    assert response.json() == {"active_count": 0, "count": 0, "alerts": []}


@pytest.mark.parametrize("minutes", ["0", "-1", "abc"])
def test_invalid_minutes_returns_422(
    make_client, fake_service, fake_repository, minutes: str
) -> None:
    client = make_client(fake_service, fake_repository, FakeAlertsRepository([], []))

    response = client.get("/api/alerts", params={"minutes": minutes})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_repository_failure_returns_generic_500(make_client, fake_service, fake_repository) -> None:
    repository = FakeAlertsRepository(resolved=[])
    repository.get_active_alerts = lambda: (_ for _ in ()).throw(RuntimeError("db locked"))
    client = make_client(fake_service, fake_repository, repository)

    response = client.get("/api/alerts")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "db locked" not in response.text
