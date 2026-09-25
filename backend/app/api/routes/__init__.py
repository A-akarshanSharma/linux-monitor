from fastapi import APIRouter

from app.api.routes import alerts, health, metrics, processes, system

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)
api_router.include_router(metrics.router)
api_router.include_router(processes.router)
api_router.include_router(health.router)
api_router.include_router(alerts.router)
