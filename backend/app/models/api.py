"""Response schemas that are specific to the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.alerts import AlertRecord
from app.models.metrics import (
    CpuMetrics,
    DiskUsage,
    MemoryMetrics,
    MetricHistoryPoint,
    NetworkMetrics,
    ProcessMetrics,
)


class CurrentMetrics(BaseModel):
    """Latest resource metrics (the same values that are stored for history graphs)."""

    collected_at: datetime
    cpu: CpuMetrics
    memory: MemoryMetrics
    disks: list[DiskUsage]
    network: NetworkMetrics


class ProcessesResponse(ProcessMetrics):
    collected_at: datetime


class MetricHistoryResponse(BaseModel):
    """Historical samples, oldest first - ready to feed straight into a chart."""

    since: datetime = Field(description="Start of the look-back window (inclusive), UTC.")
    range_minutes: int = Field(
        ge=1, description="Window actually applied; clamped to the retention period."
    )
    count: int = Field(ge=0)
    points: list[MetricHistoryPoint]


class AlertsResponse(BaseModel):
    """Currently active alerts plus recently resolved ones, most recently updated first."""

    active_count: int = Field(
        ge=0, description="Currently open alerts (WARNING or CRITICAL), any age."
    )
    count: int = Field(
        ge=0, description="active_count plus resolved alerts within the look-back window."
    )
    alerts: list[AlertRecord]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    timestamp: datetime
    uptime_seconds: float = Field(ge=0, description="Seconds since this API process started.")


class ErrorDetail(BaseModel):
    field: str = Field(description="Location of the problem, e.g. 'query.limit'.")
    message: str


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable code, e.g. 'collection_failed'.")
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """Every error returned by the API has this shape."""

    error: ErrorBody
