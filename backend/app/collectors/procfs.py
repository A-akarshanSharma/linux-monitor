"""Optional redirect so collectors read the *host's* /proc instead of the
container's own.

No-op unless ``MONITOR_HOST_PROC_PATH`` is set. Meant for the Docker "host
metrics" mode (see docker-compose.host.yml): the host's /proc is bind-mounted
read-only into the container at that path, and this points psutil at it.
This does not, on its own, restore accurate process listings or systemd/service
monitoring inside a container - see the README's Docker limitations section for
what it does and doesn't fix.
"""

from __future__ import annotations

import logging

import psutil

from app.config import Settings

logger = logging.getLogger(__name__)


def apply_host_proc_override(settings: Settings) -> None:
    if not settings.host_proc_path:
        return
    psutil.PROCFS_PATH = settings.host_proc_path
    logger.info("host_proc_override_applied", extra={"path": settings.host_proc_path})
