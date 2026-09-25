"""Default alert rules.

Each function looks at a snapshot (or, for services, a state mapping) and produces
plain ``RuleEvaluation`` data - no I/O, no notion of "already alerting" or "how long
has this been going on". The engine (engine.py) owns all of that state.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.models import MetricsSnapshot


@dataclass(frozen=True)
class RuleEvaluation:
    """One rule's judgement of the current snapshot, produced fresh every cycle."""

    rule_key: str
    target: str
    description: str
    breaching: bool
    value: float
    warning_threshold: float
    critical_threshold: float
    min_duration_seconds: int


def evaluate_cpu(snapshot: MetricsSnapshot, settings: Settings) -> RuleEvaluation:
    value = snapshot.cpu.utilization_percent
    return RuleEvaluation(
        rule_key="cpu",
        target="",
        description="CPU utilization",
        breaching=value >= settings.cpu_warning_percent,
        value=value,
        warning_threshold=settings.cpu_warning_percent,
        critical_threshold=settings.cpu_critical_percent,
        min_duration_seconds=settings.cpu_sustained_seconds,
    )


def evaluate_memory(snapshot: MetricsSnapshot, settings: Settings) -> RuleEvaluation:
    value = snapshot.memory.ram_percent
    return RuleEvaluation(
        rule_key="memory",
        target="",
        description="Memory utilization",
        breaching=value >= settings.memory_warning_percent,
        value=value,
        warning_threshold=settings.memory_warning_percent,
        critical_threshold=settings.memory_critical_percent,
        min_duration_seconds=0,
    )


def evaluate_disks(snapshot: MetricsSnapshot, settings: Settings) -> list[RuleEvaluation]:
    """One evaluation per currently-mounted disk, keyed by mount point.

    A disk that disappears between cycles (unmounted, USB drive removed) simply stops
    appearing here; see the AlertEngine docstring for what that means for any alert
    already open on it.
    """
    return [
        RuleEvaluation(
            rule_key="disk",
            target=disk.mountpoint,
            description=f"Disk usage ({disk.mountpoint})",
            breaching=disk.percent >= settings.disk_warning_percent,
            value=disk.percent,
            warning_threshold=settings.disk_warning_percent,
            critical_threshold=settings.disk_critical_percent,
            min_duration_seconds=0,
        )
        for disk in snapshot.disks
    ]


def evaluate_services(service_states: dict[str, bool]) -> list[RuleEvaluation]:
    """``service_states`` maps service name -> is running.

    Binary rather than threshold-based: any stop is CRITICAL immediately, modelled
    here as a value that always exactly meets a threshold of 1.0 (stopped) or falls
    below it (running), so it flows through the same generic severity/duration logic
    as the percentage-based rules.

    Empty until Phase 5 wires in real ``systemctl`` checks; the rule, and its dedup
    and resolve behaviour, are already fully functional.
    """
    return [
        RuleEvaluation(
            rule_key="service",
            target=name,
            description=f"Service '{name}'",
            breaching=not is_running,
            value=0.0 if is_running else 1.0,
            warning_threshold=1.0,
            critical_threshold=1.0,
            min_duration_seconds=0,
        )
        for name, is_running in service_states.items()
    ]
