from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import LiveMetricsDep
from app.models import CurrentMetrics, ErrorResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/current",
    summary="Current resource metrics",
    responses={503: {"model": ErrorResponse, "description": "Collection failed"}},
)
def get_current_metrics(service: LiveMetricsDep) -> CurrentMetrics:
    """CPU, memory, disk and network metrics. Readings are at most one second old."""
    snapshot = service.get_snapshot()
    return CurrentMetrics(
        collected_at=snapshot.collected_at,
        cpu=snapshot.cpu,
        memory=snapshot.memory,
        disks=snapshot.disks,
        network=snapshot.network,
    )
