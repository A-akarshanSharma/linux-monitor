from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AlertsRepositoryDep, SettingsDep
from app.models import AlertsResponse, ErrorResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    summary="Active and recently resolved alerts",
    responses={422: {"model": ErrorResponse, "description": "Invalid query parameter"}},
)
def list_alerts(
    repository: AlertsRepositoryDep,
    settings: SettingsDep,
    minutes: Annotated[
        int | None,
        Query(
            ge=1,
            description="Look-back window for *resolved* alerts. Active alerts are always "
            "included regardless of age. Defaults to the configured value.",
        ),
    ] = None,
) -> AlertsResponse:
    """Every currently open alert (any age), plus alerts resolved within the look-back
    window, most recently updated first - enough for both a "what's wrong right now"
    panel and a "recent alerts" feed from one call."""
    window = minutes if minutes is not None else settings.alerts_history_default_minutes
    since = datetime.now(timezone.utc) - timedelta(minutes=window)

    active = repository.get_active_alerts()
    resolved = repository.get_resolved_alerts_since(since)
    combined = sorted(active + resolved, key=lambda alert: alert.last_updated_at, reverse=True)

    return AlertsResponse(active_count=len(active), count=len(combined), alerts=combined)
