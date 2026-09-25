from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import LiveMetricsDep, MetricsRepositoryDep, SettingsDep
from app.models import CurrentMetrics, ErrorResponse, MetricHistoryResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/current",
    summary="Current resource metrics",
    responses={503: {"model": ErrorResponse, "description": "No reading collected yet"}},
)
def get_current_metrics(service: LiveMetricsDep) -> CurrentMetrics:
    """CPU, memory, disk and network metrics from the most recent collection cycle
    (at most one polling interval old)."""
    snapshot = service.get_snapshot()
    return CurrentMetrics(
        collected_at=snapshot.collected_at,
        cpu=snapshot.cpu,
        memory=snapshot.memory,
        disks=snapshot.disks,
        network=snapshot.network,
    )


@router.get(
    "/history",
    summary="Historical resource metrics",
    responses={422: {"model": ErrorResponse, "description": "Invalid query parameter"}},
)
def get_metrics_history(
    repository: MetricsRepositoryDep,
    settings: SettingsDep,
    minutes: Annotated[
        int | None,
        Query(ge=1, description="Look-back window in minutes. Defaults to the configured value."),
    ] = None,
) -> MetricHistoryResponse:
    """Stored samples, oldest first - ready to feed straight into a chart.

    ``minutes`` is silently clamped to the retention window (``retention_days``),
    since nothing older than that is ever kept.
    """
    max_minutes = settings.retention_days * 24 * 60
    requested = minutes if minutes is not None else settings.metrics_history_default_minutes
    window = min(requested, max_minutes)

    since = datetime.now(timezone.utc) - timedelta(minutes=window)
    points = repository.get_history(since)
    return MetricHistoryResponse(
        since=since, range_minutes=window, count=len(points), points=points
    )
