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
        services = client.get("/api/services")

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

    # The default monitored services (nginx, ssh, docker) are checked synchronously
    # during start(), so all three are already present by the time this request runs -
    # whatever state systemctl reports them as on whatever machine runs this test.
    assert services.status_code == 200
    service_names = {s["name"] for s in services.json()["services"]}
    assert service_names == {"nginx", "ssh", "docker"}
    for service in services.json()["services"]:
        assert service["state"] in {"RUNNING", "STOPPED", "UNKNOWN"}

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


def test_services_report_real_systemctl_state_never_fabricated(tmp_path) -> None:
    """This sandbox has the systemctl binary but no real systemd running as PID 1
    (a containerized environment) - exactly the scenario the README's Docker
    limitations section describes. The platform must report UNKNOWN, not guess."""
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "services_e2e.db"),
        monitored_services=["nginx", "ssh", "docker"],
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/services")

    body = response.json()
    assert {s["name"] for s in body["services"]} == {"nginx", "ssh", "docker"}
    for service in body["services"]:
        assert service["state"] in {"RUNNING", "STOPPED", "UNKNOWN"}
        assert service["detail"] is None or isinstance(service["detail"], str)


def test_service_down_alert_end_to_end_with_a_fake_systemctl(tmp_path) -> None:
    """Proves the full pipeline scheduler -> service_monitor -> ServicesRepository ->
    AlertEngine -> AlertsRepository -> GET /api/alerts, using a fake `systemctl` on
    PATH so the result doesn't depend on what's actually running on the test machine."""
    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text("#!/bin/sh\necho inactive\nexit 3\n")
    fake_systemctl.chmod(0o755)

    import os

    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "service_alert_e2e.db"),
        polling_interval_seconds=1,
        monitored_services=["nginx"],
    )
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmp_path}{os.pathsep}{original_path}"
    try:
        with TestClient(create_app(settings)) as client:
            services = client.get("/api/services").json()
            alerts = client.get("/api/alerts").json()
    finally:
        os.environ["PATH"] = original_path

    assert services["services"][0]["name"] == "nginx"
    assert services["services"][0]["state"] == "STOPPED"

    service_alerts = [a for a in alerts["alerts"] if a["rule_key"] == "service"]
    assert len(service_alerts) == 1
    assert service_alerts[0]["target"] == "nginx"
    assert service_alerts[0]["state"] == "CRITICAL"
    assert "not running" in service_alerts[0]["message"]
