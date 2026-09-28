from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ServicesRepositoryDep
from app.models import ServicesResponse

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", summary="Monitored service status")
def list_services(repository: ServicesRepositoryDep) -> ServicesResponse:
    """Current status of every service named in MONITOR_MONITORED_SERVICES, determined
    via `systemctl is-active`. A service the platform cannot determine the real state
    of (no systemd to talk to, unit not found, etc.) reports UNKNOWN rather than a
    guessed RUNNING or STOPPED - see the README for the Docker/WSL implications."""
    return ServicesResponse(services=repository.get_all_statuses())
