"""FastAPI application factory.

Run with ``python -m app`` or ``uvicorn app.main:create_app --factory``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.collectors.snapshot import SnapshotCollector
from app.collectors.system_info import detect_runtime_environment
from app.config import Settings, get_settings
from app.logging_config import setup_logging
from app.services.live_metrics import LiveMetricsService

logger = logging.getLogger(__name__)

DESCRIPTION = """
Read-only REST API for a Linux host monitoring platform.

Errors always use the shape `{"error": {"code", "message", "details"?}}`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings.log_level, settings.log_format)

    service = LiveMetricsService(SnapshotCollector(settings))
    service.prime()
    app.state.live_metrics = service

    logger.info(
        "application_startup",
        extra={
            "version": __version__,
            "runtime_environment": detect_runtime_environment(),
            "log_level": settings.log_level,
            "polling_interval_seconds": settings.polling_interval_seconds,
        },
    )
    yield
    logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Linux Server Monitoring & Alerting Platform",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()
    app.state.started_monotonic = time.monotonic()

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app
