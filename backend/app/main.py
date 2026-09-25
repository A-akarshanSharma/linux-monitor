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
from app.alerts.engine import AlertEngine
from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.collectors.snapshot import SnapshotCollector
from app.collectors.system_info import detect_runtime_environment
from app.config import Settings, get_database_path, get_settings
from app.database.repositories import AlertsRepository, MetricsRepository
from app.database.session import create_session_factory
from app.logging_config import setup_logging
from app.services.live_metrics import LiveMetricsService
from app.services.scheduler import MetricsScheduler

logger = logging.getLogger(__name__)

DESCRIPTION = """
Read-only REST API for a Linux host monitoring platform.

Errors always use the shape `{"error": {"code", "message", "details"?}}`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings.log_level, settings.log_format)

    db_path = get_database_path(settings)
    session_factory = create_session_factory(db_path)
    repository = MetricsRepository(session_factory)
    alerts_repository = AlertsRepository(session_factory)
    alert_engine = AlertEngine(alerts_repository, settings)

    collector = SnapshotCollector(settings)
    scheduler = MetricsScheduler(
        collector,
        repository,
        settings,
        alert_engine=alert_engine,
        alerts_repository=alerts_repository,
    )
    scheduler.start()

    app.state.scheduler = scheduler
    app.state.metrics_repository = repository
    app.state.alerts_repository = alerts_repository
    app.state.live_metrics = LiveMetricsService(scheduler.get_latest)

    logger.info(
        "application_startup",
        extra={
            "version": __version__,
            "runtime_environment": detect_runtime_environment(),
            "log_level": settings.log_level,
            "polling_interval_seconds": settings.polling_interval_seconds,
            "database_path": str(db_path),
            "retention_days": settings.retention_days,
        },
    )
    yield
    scheduler.stop()
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
