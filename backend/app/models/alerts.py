"""Alert domain models: severity used internally by the rule engine, and the
state/record shapes the API and database layer share.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """Set by the rule engine on every alert row, open or resolved."""

    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertState(str, Enum):
    """What an alert's ``state`` field can be in the API.

    NORMAL is intentionally not a value here: in this platform's alert model, NORMAL is
    the *absence* of an alert row (nothing wrong, nothing to show), never a state a
    stored alert is in. An alert is WARNING or CRITICAL while open, then RESOLVED once
    the condition clears - it is never written back to NORMAL.
    """

    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    RESOLVED = "RESOLVED"


class AlertRecord(BaseModel):
    """One alert, as read back from storage."""

    id: int
    rule_key: str = Field(description="'cpu' | 'memory' | 'disk' | 'service'.")
    target: str = Field(
        description="Empty for cpu/memory; mount point for disk; service name for service."
    )
    state: AlertState
    value: float = Field(description="Metric value that produced this row's current state.")
    threshold: float = Field(description="The threshold (warning or critical) that was crossed.")
    message: str
    first_triggered_at: datetime
    last_updated_at: datetime
    resolved_at: datetime | None = None
