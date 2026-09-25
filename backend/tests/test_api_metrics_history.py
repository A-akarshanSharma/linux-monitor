from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import FakeMetricsRepository, make_history_point

# Real "now", not a fixed date: FakeMetricsRepository filters by real time,
# same as the route computing `since = datetime.now(timezone.utc) - minutes`.
NOW = datetime.now(timezone.utc)


def test_default_window_comes_from_settings(make_client, fake_service, settings) -> None:
    points = [make_history_point(NOW - timedelta(minutes=5))]
    client = make_client(fake_service, FakeMetricsRepository(points))

    response = client.get("/api/metrics/history")

    assert response.status_code == 200
    body = response.json()
    assert body["range_minutes"] == settings.metrics_history_default_minutes == 60
    assert body["count"] == 1
    assert body["points"][0]["cpu_percent"] == points[0].cpu_percent


def test_explicit_minutes_is_applied(make_client, fake_service) -> None:
    repository = FakeMetricsRepository([])
    client = make_client(fake_service, repository)

    response = client.get("/api/metrics/history", params={"minutes": 15})

    assert response.status_code == 200
    assert response.json()["range_minutes"] == 15
    since_requested = repository.history_calls[-1]
    expected = datetime.now(timezone.utc) - timedelta(minutes=15)
    assert abs((since_requested - expected).total_seconds()) < 2


def test_minutes_beyond_retention_is_clamped_not_rejected(fake_service, settings) -> None:
    from fastapi.testclient import TestClient

    from app.api.deps import get_live_metrics, get_metrics_repository
    from app.main import create_app

    settings = settings.model_copy(update={"retention_days": 1})
    app = create_app(settings)
    app.dependency_overrides[get_live_metrics] = lambda: fake_service
    app.dependency_overrides[get_metrics_repository] = lambda: FakeMetricsRepository([])
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/metrics/history", params={"minutes": 100_000})

    assert response.status_code == 200
    assert response.json()["range_minutes"] == 1 * 24 * 60  # clamped to retention_days=1


def test_points_are_returned_in_repository_order(make_client, fake_service) -> None:
    points = [make_history_point(NOW - timedelta(minutes=m)) for m in (20, 10, 1)]
    client = make_client(fake_service, FakeMetricsRepository(points))

    body = client.get("/api/metrics/history", params={"minutes": 30}).json()

    assert [p["collected_at"][:19] for p in body["points"]] == [
        p.collected_at.isoformat()[:19] for p in points
    ]


def test_empty_history_returns_200_with_empty_list(make_client, fake_service) -> None:
    client = make_client(fake_service, FakeMetricsRepository([]))

    response = client.get("/api/metrics/history")

    assert response.status_code == 200
    assert response.json() == {
        "since": response.json()["since"],
        "range_minutes": 60,
        "count": 0,
        "points": [],
    }


@pytest.mark.parametrize("minutes", ["0", "-1", "abc"])
def test_invalid_minutes_returns_422(make_client, fake_service, minutes: str) -> None:
    client = make_client(fake_service, FakeMetricsRepository([]))

    response = client.get("/api/metrics/history", params={"minutes": minutes})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_repository_failure_returns_generic_500(make_client, fake_service) -> None:
    repository = FakeMetricsRepository(error=RuntimeError("disk I/O error"))
    client = make_client(fake_service, repository)

    response = client.get("/api/metrics/history")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "disk I/O error" not in response.text
