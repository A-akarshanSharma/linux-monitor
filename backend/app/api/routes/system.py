from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import LiveMetricsDep
from app.models import ErrorResponse, SystemInfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "",
    summary="Host information",
    responses={503: {"model": ErrorResponse, "description": "Collection failed"}},
)
def get_system(service: LiveMetricsDep) -> SystemInfo:
    """Hostname, IP address, OS, kernel, uptime and where the agent is running
    (bare host, WSL or container)."""
    return service.get_system_info()
