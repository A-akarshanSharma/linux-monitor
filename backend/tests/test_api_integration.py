"""End-to-end: real app, real lifespan, real collectors, real psutil (no fakes)."""

import logging

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

    startup = [r for r in caplog.records if r.message == "application_startup"]
    assert len(startup) == 1
    assert startup[0].runtime_environment in {"host", "wsl", "container"}
    assert any(r.message == "application_shutdown" for r in caplog.records)
