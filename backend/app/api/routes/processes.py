from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import LiveMetricsDep, SettingsDep
from app.config import MAX_TOP_PROCESSES
from app.models import ErrorResponse, ProcessesResponse

router = APIRouter(prefix="/processes", tags=["processes"])


@router.get(
    "",
    summary="Top processes",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid query parameter"},
        503: {"model": ErrorResponse, "description": "Collection failed"},
    },
)
def list_processes(
    service: LiveMetricsDep,
    settings: SettingsDep,
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=MAX_TOP_PROCESSES,
            description="Entries per list. Defaults to the configured top_processes_count.",
        ),
    ] = None,
) -> ProcessesResponse:
    """Process counts plus the top processes by CPU and by memory (RSS)."""
    size = limit if limit is not None else settings.top_processes_count
    snapshot = service.get_snapshot()
    procs = snapshot.processes
    return ProcessesResponse(
        collected_at=snapshot.collected_at,
        total_count=procs.total_count,
        running_count=procs.running_count,
        top_by_cpu=procs.top_by_cpu[:size],
        top_by_memory=procs.top_by_memory[:size],
    )
