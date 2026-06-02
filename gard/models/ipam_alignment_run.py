"""F12 IPAM alignment run ORM model."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import IpamAlignmentRunStatus, values_callable


class IpamAlignmentRun(Base):
    __tablename__ = "ipam_alignment_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    netbox_sync_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("netbox_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[IpamAlignmentRunStatus] = mapped_column(
        Enum(
            IpamAlignmentRunStatus,
            name="ipam_alignment_run_status",
            native_enum=False,
            length=32,
            values_callable=values_callable(IpamAlignmentRunStatus),
        ),
        nullable=False,
    )
    devices_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_info_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    l2vpn_available: Mapped[bool] = mapped_column(nullable=False, default=False)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'partial', 'failed', 'skipped')",
            name="ipam_alignment_runs_status",
        ),
    )
