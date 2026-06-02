"""F12 IPAM alignment finding ORM model."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import (
    AlignmentFindingKind,
    AlignmentFindingSeverity,
    AlignmentFindingStatus,
    values_callable,
)


class IpamAlignmentFinding(Base):
    __tablename__ = "ipam_alignment_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ipam_alignment_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[AlignmentFindingKind] = mapped_column(
        Enum(
            AlignmentFindingKind,
            name="alignment_finding_kind",
            native_enum=False,
            length=64,
            values_callable=values_callable(AlignmentFindingKind),
        ),
        nullable=False,
    )
    severity: Mapped[AlignmentFindingSeverity] = mapped_column(
        Enum(
            AlignmentFindingSeverity,
            name="alignment_finding_severity",
            native_enum=False,
            length=16,
            values_callable=values_callable(AlignmentFindingSeverity),
        ),
        nullable=False,
    )
    status: Mapped[AlignmentFindingStatus] = mapped_column(
        Enum(
            AlignmentFindingStatus,
            name="alignment_finding_status",
            native_enum=False,
            length=16,
            values_callable=values_callable(AlignmentFindingStatus),
        ),
        nullable=False,
    )
    netbox_observed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    gard_observed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    remediation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    interface_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('error', 'warning', 'info')",
            name="ipam_alignment_findings_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'pass')",
            name="ipam_alignment_findings_status",
        ),
    )
