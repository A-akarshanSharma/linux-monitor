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
