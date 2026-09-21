from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app import __version__
from app.models import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Liveness check")
def get_health(request: Request) -> HealthResponse:
    """Cheap liveness probe (used by Docker health checks and load balancers).

    Reports only that the API process is up and serving requests; it does not
    run a metrics collection.
    """
    return HealthResponse(
        status="ok",
        version=__version__,
        timestamp=datetime.now(timezone.utc),
        uptime_seconds=time.monotonic() - request.app.state.started_monotonic,
    )
