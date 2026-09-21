import socket
from types import SimpleNamespace

import pytest

from app.collectors import system_info


@pytest.mark.parametrize(
    ("in_container", "kernel", "expected"),
    [
        (True, "6.8.0-generic", "container"),
        (True, "5.15.153.1-microsoft-standard-WSL2", "container"),  # container wins
        (False, "5.15.153.1-microsoft-standard-WSL2", "wsl"),
        (False, "6.8.0-45-generic", "host"),
    ],
)
def test_detect_runtime_environment(
    monkeypatch: pytest.MonkeyPatch, in_container: bool, kernel: str, expected: str
) -> None:
    monkeypatch.setattr(system_info, "_is_container", lambda: in_container)
    monkeypatch.setattr(system_info.platform, "release", lambda: kernel)

    assert system_info.detect_runtime_environment() == expected


def test_os_name_prefers_pretty_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system_info.platform,
        "freedesktop_os_release",
        lambda: {"NAME": "Ubuntu", "PRETTY_NAME": "Ubuntu 24.04 LTS"},
    )

    assert system_info._read_os_name() == "Ubuntu 24.04 LTS"


def test_os_name_falls_back_when_os_release_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> dict[str, str]:
        raise OSError("no os-release")

    monkeypatch.setattr(system_info.platform, "freedesktop_os_release", missing)
    monkeypatch.setattr(system_info.platform, "system", lambda: "Linux")

    assert system_info._read_os_name() == "Linux"


def _no_route(*_args: object, **_kwargs: object) -> None:
    raise OSError("network unreachable")


def test_primary_ip_falls_back_to_interface_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_info.socket, "socket", _no_route)
    monkeypatch.setattr(
        system_info.psutil,
        "net_if_addrs",
        lambda: {
            "lo": [SimpleNamespace(family=socket.AF_INET, address="127.0.0.1")],
            "eth0": [
                SimpleNamespace(family=socket.AF_INET6, address="fe80::1"),
                SimpleNamespace(family=socket.AF_INET, address="10.0.0.5"),
            ],
        },
    )

    assert system_info.get_primary_ip() == "10.0.0.5"


def test_primary_ip_falls_back_to_loopback_when_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_info.socket, "socket", _no_route)
    monkeypatch.setattr(system_info.psutil, "net_if_addrs", lambda: {})

    assert system_info.get_primary_ip() == "127.0.0.1"


def test_collect_system_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_info.socket, "gethostname", lambda: "web-01")
    monkeypatch.setattr(system_info, "get_primary_ip", lambda: "10.1.2.3")
    monkeypatch.setattr(system_info, "_read_os_name", lambda: "Ubuntu 24.04 LTS")
    monkeypatch.setattr(system_info.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(system_info.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(system_info, "_is_container", lambda: False)
    monkeypatch.setattr(system_info.time, "time", lambda: 1_000_500.0)
    monkeypatch.setattr(system_info.psutil, "boot_time", lambda: 1_000_000.0)

    info = system_info.collect_system_info()

    assert info.hostname == "web-01"
    assert info.ip_address == "10.1.2.3"
    assert info.os_name == "Ubuntu 24.04 LTS"
    assert info.runtime_environment == "host"
    assert info.uptime_seconds == 500.0
    assert info.boot_time.tzinfo is not None
