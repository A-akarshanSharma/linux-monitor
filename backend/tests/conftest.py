"""Shared fixtures. Tests must never depend on the developer's own .env or environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(os.environ):
        if key.startswith("MONITOR_"):
            monkeypatch.delenv(key)
    # Point at a non-existent YAML file so tests only see built-in defaults.
    monkeypatch.setenv("MONITOR_CONFIG_FILE", str(tmp_path / "does-not-exist.yaml"))
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Every test gets its own throwaway SQLite file, so tests never share or
    pollute a real database and can run in parallel."""
    return Settings(_env_file=None, database_path=str(tmp_path / "test.db"))


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """setup_logging() replaces root handlers; undo that so tests don't leak into each other."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def fake_service():
    from tests.factories import FakeLiveMetrics

    return FakeLiveMetrics()


@pytest.fixture
def fake_repository():
    from tests.factories import FakeMetricsRepository

    return FakeMetricsRepository()


@pytest.fixture
def fake_alerts_repository():
    from tests.factories import FakeAlertsRepository

    return FakeAlertsRepository()


@pytest.fixture
def make_client(settings: Settings):
    """Build a TestClient wired to fakes (no real psutil, no real DB, no lifespan).

    ``raise_server_exceptions=False`` makes unhandled errors surface as the 500
    response a real client would see, instead of re-raising into the test.
    Because the app is not entered as a context manager, ``lifespan`` never
    runs - only overridden dependencies are available, which is why routes
    touching ``app.state`` directly (there are none) would fail here.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_alerts_repository, get_live_metrics, get_metrics_repository
    from app.main import create_app

    def _make(service=None, repository=None, alerts_repository=None) -> TestClient:
        app = create_app(settings)
        if service is not None:
            app.dependency_overrides[get_live_metrics] = lambda: service
        if repository is not None:
            app.dependency_overrides[get_metrics_repository] = lambda: repository
        if alerts_repository is not None:
            app.dependency_overrides[get_alerts_repository] = lambda: alerts_repository
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_client, fake_service, fake_repository, fake_alerts_repository):
    return make_client(fake_service, fake_repository, fake_alerts_repository)
