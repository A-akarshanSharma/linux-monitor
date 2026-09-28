"""Checks Linux service state via ``systemctl is-active``.

Pure and side-effect-free beyond the subprocess call itself: no database, no
logging, no notion of "did this change". A single bad or missing service name
never raises - every failure mode collapses to ``ServiceState.UNKNOWN`` with a
``detail`` string explaining why, so the caller can always get a full list back.

Why UNKNOWN instead of guessing STOPPED: `systemctl` frequently cannot answer
at all - not installed, no systemd to talk to (the common case inside a Docker
container without special setup, or WSL with systemd disabled), the unit name
doesn't exist, or the call times out. Reporting a service as "down" when the
platform actually has no idea would be exactly the kind of fabricated
functionality this project avoids; UNKNOWN says so honestly instead.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import ServiceState

DEFAULT_TIMEOUT_SECONDS = 5.0

# `systemctl is-active` prints one of these (among others) to stdout regardless
# of its exit code, which is 0 only for "active".
_RUNNING_OUTPUTS = frozenset({"active"})
_STOPPED_OUTPUTS = frozenset({"inactive", "failed", "activating", "deactivating", "reloading"})


@dataclass(frozen=True)
class ServiceCheck:
    """One fresh reading, before it's compared against anything already stored."""

    name: str
    state: ServiceState
    detail: str | None
    checked_at: datetime


def check_service(name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> ServiceCheck:
    now = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,  # a non-zero exit is the normal, informative case (e.g. "inactive")
        )
    except FileNotFoundError:
        return ServiceCheck(name, ServiceState.UNKNOWN, "systemctl is not available", now)
    except subprocess.TimeoutExpired:
        return ServiceCheck(
            name, ServiceState.UNKNOWN, f"systemctl timed out after {timeout}s", now
        )
    except OSError as exc:
        return ServiceCheck(name, ServiceState.UNKNOWN, str(exc), now)

    output = (result.stdout or "").strip().lower()
    if output in _RUNNING_OUTPUTS:
        state = ServiceState.RUNNING
    elif output in _STOPPED_OUTPUTS:
        state = ServiceState.STOPPED
    else:
        # Includes "unknown" (no such unit) and anything unrecognised - never guessed at.
        state = ServiceState.UNKNOWN

    detail = output or (result.stderr or "").strip() or None
    return ServiceCheck(name, state, detail, now)


def check_services(
    names: Iterable[str], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[ServiceCheck]:
    """Check each name independently; one failure never affects the others."""
    return [check_service(name, timeout=timeout) for name in names]
