"""Service-status domain models.

``ServiceState`` and ``ServiceRecord`` are shared by the checker (service_monitor.py),
the database layer, and the API - the same three-way split as the alert models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ServiceState(str, Enum):
    """What `systemctl is-active` told us, collapsed to three outcomes.

    UNKNOWN covers every case where the platform cannot determine the real
    state - `systemctl` missing, no systemd to talk to (common inside a
    container), the unit not existing, a timeout, anything unrecognised - and
    is never treated as "down". See the Docker/WSL limitations in the README:
    this platform reports what it can verify and never fabricates a state.
    """

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    UNKNOWN = "UNKNOWN"


class ServiceRecord(BaseModel):
    """A service's current status, as read back from storage."""

    name: str
    state: ServiceState
    detail: str | None = Field(default=None, description="Raw systemctl output or error, if any.")
    last_checked_at: datetime
    last_changed_at: datetime = Field(
        description="When `state` last differed from its previous value."
    )
