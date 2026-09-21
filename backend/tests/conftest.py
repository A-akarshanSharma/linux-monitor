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
def settings() -> Settings:
    return Settings(_env_file=None)


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
def make_client(settings: Settings):
    """Build a TestClient wired to a fake metrics service (no real psutil, no lifespan).

    ``raise_server_exceptions=False`` makes unhandled errors surface as the 500
    response a real client would see, instead of re-raising into the test.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_live_metrics
    from app.main import create_app

    def _make(service) -> TestClient:
        app = create_app(settings)
        app.dependency_overrides[get_live_metrics] = lambda: service
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_client, fake_service):
    return make_client(fake_service)
