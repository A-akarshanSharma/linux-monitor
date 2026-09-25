"""All queries live here. The rest of the app never writes SQL directly, which
is what would let SQLite be replaced by PostgreSQL later without touching
callers - only this file and session.py's connection URL would change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.orm import AlertRow, MetricSampleRow
from app.models import AlertRecord, AlertSeverity, AlertState, MetricHistoryPoint, MetricsSnapshot


def _as_utc(value: datetime) -> datetime:
    """SQLite has no native timezone-aware storage: SQLAlchemy round-trips naive
    datetimes. Everything in this table is written in UTC (collectors always
    produce UTC timestamps), so a naive value read back is re-labelled UTC
    rather than misinterpreted as local time."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _to_point(row: MetricSampleRow) -> MetricHistoryPoint:
    return MetricHistoryPoint(
        collected_at=_as_utc(row.collected_at),
        cpu_percent=row.cpu_percent,
        load_avg_1m=row.load_avg_1m,
        ram_percent=row.ram_percent,
        ram_used_bytes=row.ram_used_bytes,
        ram_total_bytes=row.ram_total_bytes,
        swap_percent=row.swap_percent,
        bytes_sent_total=row.bytes_sent_total,
        bytes_recv_total=row.bytes_recv_total,
        send_rate_bytes_per_sec=row.send_rate_bytes_per_sec,
        recv_rate_bytes_per_sec=row.recv_rate_bytes_per_sec,
        process_count=row.process_count,
    )


class MetricsRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_snapshot(self, snapshot: MetricsSnapshot) -> None:
        row = MetricSampleRow(
            collected_at=snapshot.collected_at,
            cpu_percent=snapshot.cpu.utilization_percent,
            load_avg_1m=snapshot.cpu.load_avg_1m,
            ram_percent=snapshot.memory.ram_percent,
            ram_used_bytes=snapshot.memory.ram_used_bytes,
            ram_total_bytes=snapshot.memory.ram_total_bytes,
            swap_percent=snapshot.memory.swap_percent,
            bytes_sent_total=snapshot.network.bytes_sent_total,
            bytes_recv_total=snapshot.network.bytes_recv_total,
            send_rate_bytes_per_sec=snapshot.network.send_rate_bytes_per_sec,
            recv_rate_bytes_per_sec=snapshot.network.recv_rate_bytes_per_sec,
            process_count=snapshot.processes.total_count,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()

    def get_history(self, since: datetime) -> list[MetricHistoryPoint]:
        """Samples at or after ``since``, oldest first (chart-ready order)."""
        stmt = (
            select(MetricSampleRow)
            .where(MetricSampleRow.collected_at >= since)
            .order_by(MetricSampleRow.collected_at.asc())
        )
        with self._session_factory() as session:
            rows = session.execute(stmt).scalars().all()
            return [_to_point(row) for row in rows]

    def prune_older_than(self, cutoff: datetime) -> int:
        """Delete samples older than ``cutoff``. Returns the number of rows removed."""
        with self._session_factory() as session:
            result = session.execute(
                delete(MetricSampleRow).where(MetricSampleRow.collected_at < cutoff)
            )
            session.commit()
            return result.rowcount or 0

    def count(self) -> int:
        with self._session_factory() as session:
            return session.execute(select(func.count()).select_from(MetricSampleRow)).scalar_one()


def _to_alert_record(row: AlertRow) -> AlertRecord:
    state = AlertState.RESOLVED if row.resolved_at is not None else AlertState(row.severity)
    return AlertRecord(
        id=row.id,
        rule_key=row.rule_key,
        target=row.target,
        state=state,
        value=row.value,
        threshold=row.threshold,
        message=row.message,
        first_triggered_at=_as_utc(row.first_triggered_at),
        last_updated_at=_as_utc(row.last_updated_at),
        resolved_at=_as_utc(row.resolved_at) if row.resolved_at is not None else None,
    )


@dataclass(frozen=True)
class AlertUpsertResult:
    alert_id: int
    is_new: bool
    previous_severity: AlertSeverity | None
    new_severity: AlertSeverity


@dataclass(frozen=True)
class AlertResolveResult:
    alert_id: int
    severity: AlertSeverity


class AlertsRepository:
    """One open (unresolved) row per (rule_key, target) - enforced here in application
    logic and, as a second line of defence, by a partial unique index in the schema
    (see ``AlertRow``). ``upsert_open_alert`` is what gives the alert engine "duplicate
    alert prevention": a repeated breach updates the existing row instead of inserting
    a new one.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_open_alert(
        self,
        *,
        rule_key: str,
        target: str,
        severity: AlertSeverity,
        value: float,
        threshold: float,
        message: str,
        now: datetime,
    ) -> AlertUpsertResult:
        with self._session_factory() as session:
            existing = session.execute(
                select(AlertRow).where(
                    AlertRow.rule_key == rule_key,
                    AlertRow.target == target,
                    AlertRow.resolved_at.is_(None),
                )
            ).scalar_one_or_none()

            if existing is None:
                row = AlertRow(
                    rule_key=rule_key,
                    target=target,
                    severity=severity.value,
                    value=value,
                    threshold=threshold,
                    message=message,
                    first_triggered_at=now,
                    last_updated_at=now,
                    resolved_at=None,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return AlertUpsertResult(
                    alert_id=row.id, is_new=True, previous_severity=None, new_severity=severity
                )

            previous_severity = AlertSeverity(existing.severity)
            existing.severity = severity.value
            existing.value = value
            existing.threshold = threshold
            existing.message = message
            existing.last_updated_at = now
            session.commit()
            return AlertUpsertResult(
                alert_id=existing.id,
                is_new=False,
                previous_severity=previous_severity,
                new_severity=severity,
            )

    def resolve_open_alert(
        self, rule_key: str, target: str, now: datetime
    ) -> AlertResolveResult | None:
        """Resolve the open alert for ``(rule_key, target)``, if any. Returns ``None``
        (a no-op) when there was nothing open - the normal case on every cycle where
        a rule isn't breaching."""
        with self._session_factory() as session:
            existing = session.execute(
                select(AlertRow).where(
                    AlertRow.rule_key == rule_key,
                    AlertRow.target == target,
                    AlertRow.resolved_at.is_(None),
                )
            ).scalar_one_or_none()
            if existing is None:
                return None

            existing.resolved_at = now
            existing.last_updated_at = now
            session.commit()
            return AlertResolveResult(
                alert_id=existing.id, severity=AlertSeverity(existing.severity)
            )

    def get_active_alerts(self) -> list[AlertRecord]:
        """All currently open alerts, most recently updated first. Never filtered by
        age: an alert that has been open for days is still active."""
        stmt = (
            select(AlertRow)
            .where(AlertRow.resolved_at.is_(None))
            .order_by(AlertRow.last_updated_at.desc())
        )
        with self._session_factory() as session:
            rows = session.execute(stmt).scalars().all()
            return [_to_alert_record(row) for row in rows]

    def get_resolved_alerts_since(self, since: datetime) -> list[AlertRecord]:
        stmt = (
            select(AlertRow)
            .where(AlertRow.resolved_at.is_not(None), AlertRow.resolved_at >= since)
            .order_by(AlertRow.resolved_at.desc())
        )
        with self._session_factory() as session:
            rows = session.execute(stmt).scalars().all()
            return [_to_alert_record(row) for row in rows]

    def prune_resolved_older_than(self, cutoff: datetime) -> int:
        """Delete resolved alerts older than ``cutoff``. Open alerts are never pruned,
        no matter their age. Returns the number of rows removed."""
        with self._session_factory() as session:
            result = session.execute(
                delete(AlertRow).where(
                    AlertRow.resolved_at.is_not(None), AlertRow.resolved_at < cutoff
                )
            )
            session.commit()
            return result.rowcount or 0
