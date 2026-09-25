"""Application settings.

Single source of truth for configuration. Precedence (highest wins):

    init kwargs > environment variables > .env file > config/monitor.yaml > defaults

All environment variables use the ``MONITOR_`` prefix, e.g. ``MONITOR_LOG_LEVEL``.
List values are given as comma-separated strings in the environment and as
normal YAML lists in ``monitor.yaml``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CONFIG_FILE = BACKEND_DIR / "config" / "monitor.yaml"

# Upper bound for "top N processes" lists (config value and API ?limit=).
MAX_TOP_PROCESSES = 50

DEFAULT_DISK_EXCLUDE_FSTYPES: list[str] = [
    "tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "cgroup", "cgroup2",
    "devpts", "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "pstore",
    "bpf", "autofs", "mqueue", "hugetlbfs", "ramfs", "binfmt_misc", "nsfs",
    "efivarfs", "9p", "drvfs", "fuse.*",
]  # fmt: skip


class Settings(BaseSettings):
    """Runtime configuration for the monitoring platform."""

    model_config = SettingsConfigDict(
        env_prefix="MONITOR_",
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=8000, ge=1, le=65535)

    # Relative paths resolve against the backend/ directory (see get_database_path()).
    database_path: str = "data/monitor.db"
    retention_days: int = Field(default=7, ge=1, le=365, description="How long samples are kept.")
    metrics_history_default_minutes: int = Field(
        default=60,
        ge=1,
        description="Look-back window for /api/metrics/history when ?minutes= is omitted.",
    )

    polling_interval_seconds: int = Field(default=10, ge=1, le=3600)
    top_processes_count: int = Field(default=5, ge=1, le=MAX_TOP_PROCESSES)
    disk_exclude_fstypes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_DISK_EXCLUDE_FSTYPES)
    )

    # Alert thresholds. Each metric has a warning and a critical percentage; an open
    # alert escalates from warning to critical on the same row rather than creating a
    # second one. CPU also requires a sustained breach before its first alert fires
    # (memory and disk fire on the very next collection cycle).
    cpu_warning_percent: float = Field(default=85.0, ge=0, le=100)
    cpu_critical_percent: float = Field(default=95.0, ge=0, le=100)
    cpu_sustained_seconds: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="How long CPU must stay >= cpu_warning_percent before alerting.",
    )

    memory_warning_percent: float = Field(default=90.0, ge=0, le=100)
    memory_critical_percent: float = Field(default=95.0, ge=0, le=100)

    disk_warning_percent: float = Field(default=80.0, ge=0, le=100)
    disk_critical_percent: float = Field(default=90.0, ge=0, le=100)

    alerts_history_default_minutes: int = Field(
        default=1440,
        ge=1,
        description="How far back /api/alerts looks for *resolved* alerts when ?minutes= is "
        "omitted. Active alerts are always included regardless of age.",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("disk_exclude_fstypes", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept ``"tmpfs, overlay"`` from env vars as well as real lists from YAML."""
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_alert_thresholds(self) -> Settings:
        for name, warning, critical in (
            ("cpu", self.cpu_warning_percent, self.cpu_critical_percent),
            ("memory", self.memory_warning_percent, self.memory_critical_percent),
            ("disk", self.disk_warning_percent, self.disk_critical_percent),
        ):
            if critical < warning:
                raise ValueError(
                    f"{name}_critical_percent ({critical}) must be "
                    f">= {name}_warning_percent ({warning})"
                )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlConfigSettingsSource(
            settings_cls,
            yaml_file=os.environ.get("MONITOR_CONFIG_FILE", DEFAULT_CONFIG_FILE),
        )
        return init_settings, env_settings, dotenv_settings, yaml_source


def get_database_path(settings: Settings) -> Path:
    """Resolve ``settings.database_path`` to an absolute path.

    A relative path is resolved against the backend/ directory so the database
    location does not depend on the current working directory the process was
    started from.
    """
    path = Path(settings.database_path)
    return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
