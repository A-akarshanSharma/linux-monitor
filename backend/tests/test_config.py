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


@pytest.mark.parametrize("port", ["0", "65536", "-1"])
def test_backend_port_must_be_a_valid_port(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("MONITOR_BACKEND_PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_and_history_defaults(settings: Settings) -> None:
    # `settings` fixture overrides database_path to a tmp file; everything else is default.
    assert settings.retention_days == 7
    assert settings.metrics_history_default_minutes == 60


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MONITOR_RETENTION_DAYS", "0"),
        ("MONITOR_RETENTION_DAYS", "366"),
        ("MONITOR_METRICS_HISTORY_DEFAULT_MINUTES", "0"),
    ],
)
def test_invalid_history_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_relative_database_path_resolves_against_backend_dir() -> None:
    from app.config import BACKEND_DIR, get_database_path

    settings = Settings(_env_file=None, database_path="data/monitor.db")

    assert get_database_path(settings) == BACKEND_DIR / "data" / "monitor.db"


def test_absolute_database_path_is_returned_unchanged(tmp_path: Path) -> None:
    from app.config import get_database_path

    absolute = tmp_path / "somewhere" / "monitor.db"
    settings = Settings(_env_file=None, database_path=str(absolute))

    assert get_database_path(settings) == absolute


def test_alert_threshold_defaults(settings: Settings) -> None:
    assert settings.cpu_warning_percent == 85.0
    assert settings.cpu_critical_percent == 95.0
    assert settings.cpu_sustained_seconds == 60
    assert settings.memory_warning_percent == 90.0
    assert settings.memory_critical_percent == 95.0
    assert settings.disk_warning_percent == 80.0
    assert settings.disk_critical_percent == 90.0
    assert settings.alerts_history_default_minutes == 1440


@pytest.mark.parametrize(
    ("warning_field", "critical_field"),
    [
        ("cpu_warning_percent", "cpu_critical_percent"),
        ("memory_warning_percent", "memory_critical_percent"),
        ("disk_warning_percent", "disk_critical_percent"),
    ],
)
def test_critical_below_warning_is_rejected(warning_field: str, critical_field: str) -> None:
    with pytest.raises(ValidationError, match=critical_field):
        Settings(_env_file=None, **{warning_field: 90.0, critical_field: 80.0})


def test_critical_equal_to_warning_is_allowed() -> None:
    settings = Settings(_env_file=None, memory_warning_percent=90.0, memory_critical_percent=90.0)

    assert settings.memory_critical_percent == 90.0


def test_env_vars_override_alert_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONITOR_CPU_WARNING_PERCENT", "70")
    monkeypatch.setenv("MONITOR_CPU_SUSTAINED_SECONDS", "30")

    settings = Settings(_env_file=None)

    assert settings.cpu_warning_percent == 70.0
    assert settings.cpu_sustained_seconds == 30
