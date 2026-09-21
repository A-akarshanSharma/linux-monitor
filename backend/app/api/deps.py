"""FastAPI dependencies. Routes depend on these, so tests can override them."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.services.live_metrics import LiveMetricsService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_live_metrics(request: Request) -> LiveMetricsService:
    return request.app.state.live_metrics  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
LiveMetricsDep = Annotated[LiveMetricsService, Depends(get_live_metrics)]
