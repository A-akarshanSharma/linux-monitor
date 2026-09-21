"""Response schemas that are specific to the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.metrics import CpuMetrics, DiskUsage, MemoryMetrics, NetworkMetrics, ProcessMetrics


class CurrentMetrics(BaseModel):
    """Latest resource metrics (the same values that are stored for history graphs)."""

    collected_at: datetime
    cpu: CpuMetrics
    memory: MemoryMetrics
    disks: list[DiskUsage]
    network: NetworkMetrics


class ProcessesResponse(ProcessMetrics):
    collected_at: datetime


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
