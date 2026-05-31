"""`uplift_exceptions` — operator-accepted known-risk override (F5).

One row per filed exception. The state machine
(`pending_review` → `approved` | `rejected` | `withdrawn` | `expired`)
is enforced at three layers (ADR-0016 §C); this row carries the
**DB-level** layer via the SoD CHECK and the
`ck_uplift_exceptions_blocker_one_of` XOR (a row references either a
catalogue rule by id OR a synthetic blocker kind, never both, never
neither).

Expiry is lazy: the F4 readiness controller transitions
`approved → expired` on next evaluate when `expires_at < now()`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class UpliftException(Base):
    __tablename__ = "uplift_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )

    # XOR with synthetic_kind — see ck_uplift_exceptions_blocker_one_of.
    blocker_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("firmware_prerequisite_rules.id", ondelete="RESTRICT"), nullable=True
    )
    # When the blocker is synthetic (e.g. missing_upgrade_path,
    # missing_observation_field) and has no catalogue rule row.
    synthetic_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)

    justification: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")

    filed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    filed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rejected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    withdrawn_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    expired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('pending_review','approved','rejected','expired','withdrawn')",
            name="ck_uplift_exceptions_state",
        ),
        CheckConstraint(
            "(blocker_rule_id IS NOT NULL)::int + (synthetic_kind IS NOT NULL)::int = 1",
            name="ck_uplift_exceptions_blocker_one_of",
        ),
        CheckConstraint(
            "synthetic_kind IS NULL OR synthetic_kind IN "
            "('missing_upgrade_path','missing_observation_field')",
            name="ck_uplift_exceptions_synthetic_kind_valid",
        ),
        CheckConstraint(
            "length(justification) BETWEEN 20 AND 2000",
            name="ck_uplift_exceptions_justification_len",
        ),
        CheckConstraint(
            "expires_at > filed_at",
            name="ck_uplift_exceptions_expires_after_filed",
        ),
        CheckConstraint(
            "expires_at <= filed_at + interval '365 days'",
            name="ck_uplift_exceptions_max_lifetime_365d",
        ),
        CheckConstraint(
            "approved_by IS NULL OR approved_by <> filed_by",
            name="ck_uplift_exceptions_sod",
        ),
        Index("ix_uplift_exceptions_device_state", "device_id", "state"),
        Index(
            "ix_uplift_exceptions_expires_at",
            "expires_at",
            postgresql_where=text("state = 'approved'"),
        ),
        Index(
            "uq_uplift_exceptions_one_active_per_blocker",
            "device_id",
            text("coalesce(blocker_rule_id::text, synthetic_kind)"),
            unique=True,
            postgresql_where=text("state = 'approved'"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UpliftException id={self.id} device={self.device_id} state={self.state}>"
