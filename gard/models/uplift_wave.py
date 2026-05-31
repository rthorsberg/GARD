"""`uplift_waves` — the reviewable batch with strict state machine (F5).

One row per wave. The `state` column is the live verdict; every
transition writes its dedicated `<state>_by` + `<state>_at` columns,
so the row itself carries the full lifecycle without joining an
auxiliary history table (the immutable audit chain in `audit_events`
plays that role).

ADR-0016 §B installs separation-of-duties at three layers; this row
carries the **DB-level** guarantee via `ck_uplift_waves_sod` plus
`ck_uplift_waves_terminal_consistency` to ensure every terminal state
has a matching timestamp.

The change window grammar (`ck_uplift_waves_change_window_*`) is the
floor: 15min ≤ duration ≤ 24h, UTC, future-dated. Application layer
adds the "future-dated" requirement because Postgres CHECKs can't
reference `now()`.
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class UpliftWave(Base):
    __tablename__ = "uplift_waves"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uplift_plans.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_platform_family: Mapped[str] = mapped_column(String(64), nullable=False)

    change_window_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    change_window_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The DB CHECK is the authority for legal values.
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    drafted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    drafted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    submitted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_citation: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    rejected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_citation: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    cancelled_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    invalidated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidated_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','submitted','approved','rejected','cancelled','invalidated')",
            name="ck_uplift_waves_state",
        ),
        CheckConstraint(
            "change_window_end > change_window_start",
            name="ck_uplift_waves_change_window_order",
        ),
        CheckConstraint(
            "change_window_end - change_window_start <= interval '24 hours'",
            name="ck_uplift_waves_change_window_max_24h",
        ),
        CheckConstraint(
            "change_window_end - change_window_start >= interval '15 minutes'",
            name="ck_uplift_waves_change_window_min_15m",
        ),
        CheckConstraint(
            "approval_citation IS NULL OR length(approval_citation) BETWEEN 20 AND 2000",
            name="ck_uplift_waves_approval_citation_len",
        ),
        CheckConstraint(
            "rejection_citation IS NULL OR length(rejection_citation) BETWEEN 20 AND 2000",
            name="ck_uplift_waves_rejection_citation_len",
        ),
        CheckConstraint(
            "cancellation_reason IS NULL OR length(cancellation_reason) BETWEEN 10 AND 500",
            name="ck_uplift_waves_cancellation_reason_len",
        ),
        CheckConstraint(
            "approved_by IS NULL OR approved_by <> drafted_by",
            name="ck_uplift_waves_sod",
        ),
        CheckConstraint(
            "("
            "  (state <> 'approved')      OR approved_at      IS NOT NULL"
            ") AND ("
            "  (state <> 'rejected')      OR rejected_at      IS NOT NULL"
            ") AND ("
            "  (state <> 'cancelled')     OR cancelled_at     IS NOT NULL"
            ") AND ("
            "  (state <> 'invalidated')   OR invalidated_at   IS NOT NULL"
            ") AND ("
            "  (state <> 'submitted')     OR submitted_at     IS NOT NULL"
            ")",
            name="ck_uplift_waves_terminal_consistency",
        ),
        Index("ix_uplift_waves_plan_state", "plan_id", "state"),
        Index(
            "ix_uplift_waves_state_drafted_at_desc",
            "state",
            text("drafted_at DESC"),
        ),
        Index(
            "ix_uplift_waves_target_version",
            "target_platform_family",
            "target_version",
        ),
        Index(
            "uq_uplift_waves_plan_idempotency",
            "plan_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_uplift_waves_plan_name",
            "plan_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<UpliftWave id={self.id} plan={self.plan_id} "
            f"state={self.state} target={self.target_version}>"
        )
