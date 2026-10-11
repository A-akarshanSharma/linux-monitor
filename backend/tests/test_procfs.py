import pytest

from app.collectors import procfs
from app.config import Settings


def test_no_override_when_host_proc_path_is_empty(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr(procfs.psutil, "PROCFS_PATH", "/proc")

    procfs.apply_host_proc_override(settings)

    assert procfs.psutil.PROCFS_PATH == "/proc"


def test_override_sets_procfs_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procfs.psutil, "PROCFS_PATH", "/proc")
    settings = Settings(_env_file=None, host_proc_path="/host/proc")

    procfs.apply_host_proc_override(settings)

    assert procfs.psutil.PROCFS_PATH == "/host/proc"


def test_default_host_proc_path_is_empty(settings: Settings) -> None:
    assert settings.host_proc_path == ""
