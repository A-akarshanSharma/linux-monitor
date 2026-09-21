"""Host identity: hostname, OS, IP address, uptime, runtime environment."""

from __future__ import annotations

import platform
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from app.models import RuntimeEnvironment, SystemInfo

_FALLBACK_IP = "127.0.0.1"


def _is_container() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def detect_runtime_environment() -> RuntimeEnvironment:
    """Best-effort detection of container / WSL / plain host."""
    if _is_container():
        return "container"
    if "microsoft" in platform.release().lower():
        return "wsl"
    return "host"


def _read_os_name() -> str:
    try:
        info = platform.freedesktop_os_release()
    except OSError:  # /etc/os-release missing (minimal images, non-Linux)
        return platform.system() or "Unknown"
    return info.get("PRETTY_NAME") or info.get("NAME") or platform.system() or "Unknown"


def get_primary_ip() -> str:
    """Return the IPv4 address used for outbound traffic.

    Connecting a UDP socket does not send any packet; it only asks the kernel
    which local address the default route would use. Falls back to the first
    non-loopback interface address, then to 127.0.0.1 (e.g. no network).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        pass

    for addresses in psutil.net_if_addrs().values():
        for addr in addresses:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                return addr.address
    return _FALLBACK_IP


def collect_system_info() -> SystemInfo:
    boot_ts = psutil.boot_time()
    return SystemInfo(
        hostname=socket.gethostname(),
        ip_address=get_primary_ip(),
        os_name=_read_os_name(),
        kernel=platform.release(),
        architecture=platform.machine(),
        runtime_environment=detect_runtime_environment(),
        boot_time=datetime.fromtimestamp(boot_ts, tz=timezone.utc),
        uptime_seconds=max(time.time() - boot_ts, 0.0),
    )
