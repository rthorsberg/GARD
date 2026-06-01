"""`netbox_sync_runs` — one NetBox pull/reconcile attempt."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import NetboxSyncRunStatus


class NetboxSyncRun(Base):
    __tablename__ = "netbox_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    status: Mapped[NetboxSyncRunStatus] = mapped_column(
        Enum(
            NetboxSyncRunStatus,
            name="netbox_sync_run_status",
            native_enum=False,
            length=32,
            values_callable=lambda x: [m.value for m in NetboxSyncRunStatus],
        ),
        nullable=False,
    )
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orphaned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    writeback_updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    writeback_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    writeback_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    writeback_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="netbox_sync_runs_status",
        ),
    )
