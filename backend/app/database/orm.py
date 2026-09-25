"""SQLAlchemy table definitions.

Kept intentionally small: one row per collection cycle, with the fields the
dashboard's charts need (CPU, memory, network). Per-process and per-disk
detail is not historised - those are "current state", served live from
``/api/processes`` and ``/api/system``, not graphed over time.

Swapping SQLite for PostgreSQL later means changing the connection URL in
``session.py``; nothing here is SQLite-specific.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MetricSampleRow(Base):
    """One resource-usage reading. Always stored and read back as UTC (see repositories.py)."""

    __tablename__ = "metric_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    load_avg_1m: Mapped[float] = mapped_column(Float, nullable=False)

    ram_percent: Mapped[float] = mapped_column(Float, nullable=False)
    ram_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ram_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    swap_percent: Mapped[float] = mapped_column(Float, nullable=False)

    bytes_sent_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bytes_recv_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    send_rate_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    recv_rate_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    process_count: Mapped[int] = mapped_column(Integer, nullable=False)


class AlertRow(Base):
    """One alert. ``severity`` holds WARNING/CRITICAL for the life of the row (including
    after it resolves, as a record of how bad it got); ``resolved_at`` is what actually
    marks it resolved.

    The partial unique index enforces "one open alert per (rule_key, target)" - the same
    invariant the application maintains - as a second line of defence at the database
    level (SQLite supports partial indexes; a plain UNIQUE constraint could not express
    "unique only while resolved_at IS NULL").
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index(
            "ix_alerts_open_unique",
            "rule_key",
            "target",
            unique=True,
            sqlite_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)

    first_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
