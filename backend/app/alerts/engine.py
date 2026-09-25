"""Turns rule evaluations into alert lifecycle events (create / escalate / resolve).

Called once per collection cycle by the scheduler. Owns the only piece of state a
rule needs that the database doesn't naturally give it: how long a not-yet-alerting
condition has been continuously breaching (see ``cpu_sustained_seconds``).

Known limitation: if a rule's target stops being observed entirely (a disk is
unmounted, a service is dropped from the monitored list), any alert already open for
it is never automatically resolved, since no further evaluation is produced for that
target to trigger the resolve path. It would still show as active until the platform
is restarted or the situation is handled manually. Reconciling "keys that used to
exist" against "keys still open in the database" every cycle would close this gap,
but adds a query and some complexity for an edge case; documented here rather than
solved, matching the project's habit of not overengineering.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.alerts.rules import (
    RuleEvaluation,
    evaluate_cpu,
    evaluate_disks,
    evaluate_memory,
    evaluate_services,
)
from app.config import Settings
from app.database.repositories import AlertsRepository
from app.models import AlertSeverity, MetricsSnapshot

logger = logging.getLogger(__name__)


def _build_message(evaluation: RuleEvaluation, severity: AlertSeverity) -> str:
    if evaluation.rule_key == "service":
        return f"{evaluation.description} is not running"
    threshold = (
        evaluation.critical_threshold
        if severity is AlertSeverity.CRITICAL
        else evaluation.warning_threshold
    )
    return (
        f"{evaluation.description} at {evaluation.value:.1f}% "
        f"(>= {threshold:.0f}% {severity.value.lower()} threshold)"
    )


class AlertEngine:
    def __init__(
        self,
        repository: AlertsRepository,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._clock = clock
        # (rule_key, target) -> when a breach that hasn't yet reached its
        # min_duration_seconds started. Only ever non-trivial for CPU today.
        self._breach_since: dict[tuple[str, str], datetime] = {}

    def evaluate(
        self, snapshot: MetricsSnapshot, service_states: dict[str, bool] | None = None
    ) -> None:
        evaluations: list[RuleEvaluation] = [
            evaluate_cpu(snapshot, self._settings),
            evaluate_memory(snapshot, self._settings),
            *evaluate_disks(snapshot, self._settings),
            *evaluate_services(service_states or {}),
        ]

        # Targets that no longer produced an evaluation this cycle (e.g. a disk that
        # was unmounted) still need their pending-breach timer cleared, so that if the
        # same target reappears later it starts counting from zero rather than resuming
        # a stale timer.
        seen_keys = {(e.rule_key, e.target) for e in evaluations}
        for key in [k for k in self._breach_since if k not in seen_keys]:
            del self._breach_since[key]

        for evaluation in evaluations:
            self._process(evaluation)

    def _process(self, evaluation: RuleEvaluation) -> None:
        key = (evaluation.rule_key, evaluation.target)
        now = self._clock()

        if not evaluation.breaching:
            self._breach_since.pop(key, None)
            result = self._repository.resolve_open_alert(
                evaluation.rule_key, evaluation.target, now
            )
            if result is not None:
                logger.info(
                    "alert_resolved",
                    extra={
                        "alert_id": result.alert_id,
                        "rule_key": evaluation.rule_key,
                        "target": evaluation.target,
                        "severity": result.severity.value,
                    },
                )
            return

        started_at = self._breach_since.setdefault(key, now)
        if (now - started_at).total_seconds() < evaluation.min_duration_seconds:
            return  # breaching, but not yet held long enough to alert

        severity = (
            AlertSeverity.CRITICAL
            if evaluation.value >= evaluation.critical_threshold
            else AlertSeverity.WARNING
        )
        threshold = (
            evaluation.critical_threshold
            if severity is AlertSeverity.CRITICAL
            else evaluation.warning_threshold
        )
        result = self._repository.upsert_open_alert(
            rule_key=evaluation.rule_key,
            target=evaluation.target,
            severity=severity,
            value=evaluation.value,
            threshold=threshold,
            message=_build_message(evaluation, severity),
            now=now,
        )

        if result.is_new:
            logger.info(
                "alert_created",
                extra={
                    "alert_id": result.alert_id,
                    "rule_key": evaluation.rule_key,
                    "target": evaluation.target,
                    "severity": severity.value,
                    "value": evaluation.value,
                },
            )
        elif result.previous_severity != result.new_severity:
            logger.info(
                "alert_severity_changed",
                extra={
                    "alert_id": result.alert_id,
                    "rule_key": evaluation.rule_key,
                    "target": evaluation.target,
                    "from": result.previous_severity.value,
                    "to": result.new_severity.value,
                },
            )
        # else: still breaching at the same severity - repository row was refreshed
        # (value/timestamp), but nothing about this cycle is worth a log line.
