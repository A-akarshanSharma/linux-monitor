from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_CONFIG_FILE, Settings


def test_defaults(settings: Settings) -> None:
    assert settings.polling_interval_seconds == 10
    assert settings.top_processes_count == 5
    assert settings.log_level == "INFO"
    assert "tmpfs" in settings.disk_exclude_fstypes


def test_yaml_overrides_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    yaml_file = tmp_path / "monitor.yaml"
    yaml_file.write_text("polling_interval_seconds: 30\ntop_processes_count: 8\n")
    monkeypatch.setenv("MONITOR_CONFIG_FILE", str(yaml_file))

    settings = Settings(_env_file=None)

    assert settings.polling_interval_seconds == 30
    assert settings.top_processes_count == 8


def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    yaml_file = tmp_path / "monitor.yaml"
    yaml_file.write_text("polling_interval_seconds: 30\n")
    monkeypatch.setenv("MONITOR_CONFIG_FILE", str(yaml_file))
    monkeypatch.setenv("MONITOR_POLLING_INTERVAL_SECONDS", "5")

    assert Settings(_env_file=None).polling_interval_seconds == 5


def test_env_list_is_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONITOR_DISK_EXCLUDE_FSTYPES", "TmpFS, overlay ,, fuse.*")

    assert Settings(_env_file=None).disk_exclude_fstypes == ["tmpfs", "overlay", "fuse.*"]


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONITOR_LOG_LEVEL", "debug")

    assert Settings(_env_file=None).log_level == "DEBUG"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MONITOR_POLLING_INTERVAL_SECONDS", "0"),
        ("MONITOR_TOP_PROCESSES_COUNT", "1000"),
        ("MONITOR_LOG_LEVEL", "LOUD"),
        ("MONITOR_LOG_FORMAT", "xml"),
    ],
)
def test_invalid_values_are_rejected(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_shipped_yaml_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed monitor.yaml must always load cleanly."""
    monkeypatch.setenv("MONITOR_CONFIG_FILE", str(DEFAULT_CONFIG_FILE))

    settings = Settings(_env_file=None)

    assert settings.polling_interval_seconds >= 1
    assert "fuse.*" in settings.disk_exclude_fstypes
