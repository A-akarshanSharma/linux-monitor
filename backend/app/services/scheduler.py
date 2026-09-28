"""Background collection loop.

Owns the single ``SnapshotCollector`` instance for the process. On its own
thread it collects on a fixed interval, keeps the latest reading in memory for
the live API endpoints, persists every reading for ``/api/metrics/history``,
checks configured Linux services, and (if an ``AlertEngine`` is supplied)
evaluates alert rules against the snapshot and current service states.
A `threading.Event` is used for the wait so `stop()` interrupts it immediately
instead of waiting out the rest of the current interval.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.collectors.snapshot import CollectionError, SnapshotCollector
from app.config import Settings
from app.database.repositories import AlertsRepository, MetricsRepository, ServicesRepository
from app.models import MetricsSnapshot, ServiceState
from app.services.service_monitor import check_services

if TYPE_CHECKING:
    from app.alerts.engine import AlertEngine

logger = logging.getLogger(__name__)


class MetricsScheduler:
    def __init__(
        self,
        collector: SnapshotCollector,
        repository: MetricsRepository,
        settings: Settings,
        *,
        alert_engine: AlertEngine | None = None,
        alerts_repository: AlertsRepository | None = None,
        services_repository: ServicesRepository | None = None,
        monitored_service_names: Sequence[str] = (),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._collector = collector
        self._repository = repository
        self._alert_engine = alert_engine
        self._alerts_repository = alerts_repository
        self._services_repository = services_repository
        self._monitored_service_names = list(monitored_service_names)
        self._interval_seconds = settings.polling_interval_seconds
        self._retention = timedelta(days=settings.retention_days)
        self._clock = clock

        self._lock = threading.Lock()
        self._latest: MetricsSnapshot | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Prime the collector, take one reading immediately, then start the background loop.

        Blocking briefly here (at most ~1s) means the very first API request
        after start-up already has a real reading, rather than a 503 until the
        first interval elapses.
        """
        self._collector.prime()
        self._stop_event.wait(min(1.0, self._interval_seconds))
        self._collect_once()

        self._thread = threading.Thread(target=self._run, name="metrics-scheduler", daemon=True)
        self._thread.start()
        logger.info("scheduler_started", extra={"interval_seconds": self._interval_seconds})

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("scheduler_stopped")

    def get_latest(self) -> MetricsSnapshot:
        """Return the most recently collected snapshot.

        Raises :class:`CollectionError` if nothing has been collected yet
        (only possible if every attempt so far has failed).
        """
        with self._lock:
            if self._latest is None:
                raise CollectionError("scheduler", RuntimeError("no metrics collected yet"))
            return self._latest

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            self._collect_once()

    def _collect_once(self) -> None:
        try:
            snapshot = self._collector.collect()
        except CollectionError as exc:
            logger.error(
                "metric_collection_failed", extra={"collector": exc.collector, "error": str(exc)}
            )
            return

        with self._lock:
            self._latest = snapshot

        try:
            self._repository.save_snapshot(snapshot)
            cutoff = self._clock() - self._retention
            deleted = self._repository.prune_older_than(cutoff)
            if deleted:
                logger.info("metrics_pruned", extra={"rows_deleted": deleted})
        except Exception:
            # The live reading above already succeeded; a storage failure should not
            # take the API down, only the history feature for this one cycle.
            logger.exception("metrics_persist_failed")

        service_states = self._check_services()

        if self._alert_engine is not None:
            try:
                self._alert_engine.evaluate(snapshot, service_states=service_states)
            except Exception:
                # A bug in rule evaluation must never take down metric collection.
                logger.exception("alert_evaluation_failed")

        if self._alerts_repository is not None:
            try:
                cutoff = self._clock() - self._retention
                deleted = self._alerts_repository.prune_resolved_older_than(cutoff)
                if deleted:
                    logger.info("alerts_pruned", extra={"rows_deleted": deleted})
            except Exception:
                logger.exception("alerts_prune_failed")

    def _check_services(self) -> dict[str, bool]:
        """Check every configured service, persist its status, log any state change,
        and return a name -> is_running map for the alert engine (if any).

        Runs on every cycle regardless of whether an alert engine is configured,
        since /api/services depends on it independently of alerting.

        A service whose state came back UNKNOWN is left out of the returned map
        entirely, rather than guessed as either running or stopped: the alert
        engine only evaluates rules for names it's given, so an UNKNOWN service
        simply isn't judged this cycle. If it has an alert already open from
        before it went UNKNOWN, that alert is intentionally left open rather than
        auto-resolved on inconclusive data (see AlertEngine's docstring).
        """
        if self._services_repository is None or not self._monitored_service_names:
            return {}

        service_states: dict[str, bool] = {}
        try:
            checks = check_services(self._monitored_service_names)
        except Exception:
            logger.exception("service_check_failed")
            return {}

        for check in checks:
            try:
                result = self._services_repository.upsert_status(
                    name=check.name, state=check.state, detail=check.detail, now=check.checked_at
                )
                if result.changed:
                    logger.info(
                        "service_state_changed",
                        extra={
                            "service_name": check.name,
                            "previous": result.previous_state.value
                            if result.previous_state
                            else None,
                            "new": result.new_state.value,
                        },
                    )
            except Exception:
                logger.exception(
                    "service_status_persist_failed", extra={"service_name": check.name}
                )

            if check.state is not ServiceState.UNKNOWN:
                service_states[check.name] = check.state is ServiceState.RUNNING

        return service_states
