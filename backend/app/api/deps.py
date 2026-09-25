"""FastAPI dependencies. Routes depend on these, so tests can override them."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.database.repositories import AlertsRepository, MetricsRepository
from app.services.live_metrics import LiveMetricsService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_live_metrics(request: Request) -> LiveMetricsService:
    return request.app.state.live_metrics  # type: ignore[no-any-return]


def get_metrics_repository(request: Request) -> MetricsRepository:
    return request.app.state.metrics_repository  # type: ignore[no-any-return]


def get_alerts_repository(request: Request) -> AlertsRepository:
    return request.app.state.alerts_repository  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
LiveMetricsDep = Annotated[LiveMetricsService, Depends(get_live_metrics)]
MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]
AlertsRepositoryDep = Annotated[AlertsRepository, Depends(get_alerts_repository)]
