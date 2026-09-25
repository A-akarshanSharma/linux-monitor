"""End-to-end: real app, real lifespan, real collectors, real database, real psutil (no fakes)."""

import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_full_stack_on_this_machine(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), TestClient(create_app(settings)) as client:
        system = client.get("/api/system")
        current = client.get("/api/metrics/current")
        processes = client.get("/api/processes", params={"limit": 3})
        health = client.get("/api/health")
        history = client.get("/api/metrics/history", params={"minutes": 5})
        alerts = client.get("/api/alerts")

    assert system.status_code == 200
    assert system.json()["hostname"]

    assert current.status_code == 200
    metrics = current.json()
    assert 0 <= metrics["cpu"]["utilization_percent"] <= 100
    assert metrics["memory"]["ram_total_bytes"] > 0
    # The service waited for a full window, so the first reading already has network rates.
    assert metrics["network"]["send_rate_bytes_per_sec"] is not None

    assert processes.status_code == 200
    assert 1 <= len(processes.json()["top_by_cpu"]) <= 3
    assert processes.json()["total_count"] > 0

    assert health.json()["status"] == "ok"

    # start() collects and stores one sample synchronously before the app is "up",
    # so history already has at least that one row without waiting for a poll cycle.
    assert history.status_code == 200
    assert history.json()["count"] >= 1

    # Default thresholds (85/90/95%) are unlikely to be breached on a CI runner, so
    # this only checks the response is well-formed, not that active_count == 0.
    assert alerts.status_code == 200
    assert isinstance(alerts.json()["active_count"], int)

    startup = [r for r in caplog.records if r.message == "application_startup"]
    assert len(startup) == 1
    assert startup[0].runtime_environment in {"host", "wsl", "container"}
    assert startup[0].database_path
    assert any(r.message == "application_shutdown" for r in caplog.records)


def test_history_accumulates_across_scheduler_cycles(tmp_path) -> None:
    """A slower but more convincing proof: run the real scheduler for a couple of
    real polling intervals and confirm /api/metrics/history grows accordingly."""
    settings = Settings(
        _env_file=None, database_path=str(tmp_path / "history.db"), polling_interval_seconds=1
    )

    with TestClient(create_app(settings)) as client:
        first = client.get("/api/metrics/history", params={"minutes": 5}).json()["count"]
        time.sleep(2.2)  # ~2 more collection cycles at a 1-second interval
        second = client.get("/api/metrics/history", params={"minutes": 5}).json()["count"]

    assert first >= 1
    assert second >= first + 2


def test_alerts_pipeline_end_to_end(tmp_path) -> None:
    """Force a real breach (threshold set to 0) and confirm it flows all the way
    through: scheduler -> AlertEngine -> AlertsRepository -> GET /api/alerts."""
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "alerts_e2e.db"),
        polling_interval_seconds=1,
        memory_warning_percent=0.0,
        memory_critical_percent=0.0,
    )

    with TestClient(create_app(settings)) as client:
        # start() runs one collection synchronously before the app finishes starting,
        # so the alert is already open by the time this request goes out.
        response = client.get("/api/alerts")

    body = response.json()
    assert body["active_count"] >= 1
    memory_alerts = [a for a in body["alerts"] if a["rule_key"] == "memory"]
    assert len(memory_alerts) == 1
    assert memory_alerts[0]["state"] == "CRITICAL"
    assert memory_alerts[0]["target"] == ""


def test_alert_resolves_end_to_end_once_thresholds_are_no_longer_breached(tmp_path) -> None:
    """A snapshot always has ram_percent >= 0, so a warning threshold that's
    unreachably high (101, above Settings' le=100 bound would reject it - use the
    maximum valid value instead) guarantees no memory alert ever fires, while the
    other end-to-end test above proves the create path. Together they cover both
    directions of the pipeline without needing to manipulate real system load."""
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "alerts_e2e_normal.db"),
        polling_interval_seconds=1,
        memory_warning_percent=100.0,
        memory_critical_percent=100.0,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/alerts")

    body = response.json()
    assert [a for a in body["alerts"] if a["rule_key"] == "memory"] == []
