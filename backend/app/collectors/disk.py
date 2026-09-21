"""Disk usage for real, mounted filesystems."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from fnmatch import fnmatchcase

import psutil

from app.models import DiskUsage

logger = logging.getLogger(__name__)

# Mount points that never hold user-relevant capacity (snap loop mounts, kernel
# interfaces, container internals). Matched on path-component boundaries.
_EXCLUDED_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/snap", "/var/lib/docker")


def _is_excluded_mount(mountpoint: str) -> bool:
    return any(
        mountpoint == prefix or mountpoint.startswith(prefix + "/")
        for prefix in _EXCLUDED_MOUNT_PREFIXES
    )


def _is_excluded_fstype(fstype: str, patterns: list[str]) -> bool:
    """Match an fstype against exclude patterns; ``*`` wildcards are supported (``fuse.*``)."""
    return any(fnmatchcase(fstype.lower(), pattern) for pattern in patterns)


def collect_disks(exclude_fstypes: Iterable[str]) -> list[DiskUsage]:
    """Return usage for each real mounted filesystem.

    * Pseudo filesystems (tmpfs, overlay, squashfs, fuse.*, ...) are skipped,
      otherwise e.g. read-only snap images sit at 100% and trigger permanent alerts.
    * The same device mounted in several places (bind mounts) is reported once,
      using its shortest mount path.
    * Mounts that cannot be read are logged and skipped, not fatal.
    """
    excluded_fstypes = [fstype.lower() for fstype in exclude_fstypes]
    partitions = sorted(
        psutil.disk_partitions(all=True), key=lambda p: (len(p.mountpoint), p.mountpoint)
    )

    seen_devices: set[str] = set()
    disks: list[DiskUsage] = []
    for part in partitions:
        if _is_excluded_fstype(part.fstype, excluded_fstypes) or _is_excluded_mount(
            part.mountpoint
        ):
            continue
        if part.device in seen_devices:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError as exc:
            logger.warning(
                "disk_usage_unavailable",
                extra={"mountpoint": part.mountpoint, "error": str(exc)},
            )
            continue
        if usage.total == 0:
            continue

        seen_devices.add(part.device)
        disks.append(
            DiskUsage(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                percent=usage.percent,
            )
        )
    return sorted(disks, key=lambda d: d.mountpoint)
