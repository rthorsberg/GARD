"""`readiness_evaluations` — append-only readiness verdict rows (F4).

One row per evaluation pass that changed the device's readiness state,
blockers, recommended actions, applicable rules count, or upgrade-path
reachability. Silent (no row, no audit) for re-evaluations against
unchanged inputs (R-5 idempotency).

The latest row per device, ordered by ``evaluated_at DESC``, is the
live verdict that the REST + MCP surfaces return. Older rows form the
verdict history (e.g. "when did r1.oslo first show as blocked-by-RAM?").

Written by the regular ``gard_writer`` role — this is a derived-state
cache, not chain-of-custody evidence; the audit chain in
``audit_events`` is the immutable record (ADR-0009).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class ReadinessEvaluation(Base):
    __tablename__ = "readiness_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    # FK into the F3 row that this readiness verdict was derived from.
    # SET NULL on delete so a pruned F3 cache leaves F4 evidence intact.
    compliance_evaluation_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_evaluations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # `ready_for_uplift` | `blocked` | `not_applicable`. The DB CHECK
    # constraint is the authority.
    readiness_state: Mapped[str] = mapped_column(String(32), nullable=False)

    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    upgrade_path_exists: Mapped[bool] = mapped_column(Boolean, nullable=False)
    applicable_rules_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSONB list of Blocker dicts. Sorted per R-1 (severity desc,
    # predicate_kind index asc, rule_id asc).
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # JSONB list of RecommendedAction dicts. Sorted per R-7.
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # JSONB list of ComplianceReason-shaped dicts (carries F3-style
    # `kind` / `detail` for the `not_applicable` branch reasons and any
    # supplementary signals).
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    # 0.0..1.0; v1 always 1.0 (deterministic rules, no inference).
    confidence: Mapped[decimal.Decimal] = mapped_column(Numeric(3, 2), nullable=False)

    evaluated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index(
            "ix_readiness_evaluations_device_evaluated_desc",
            "device_id",
            text("evaluated_at DESC"),
        ),
        Index(
            "ix_readiness_evaluations_state",
            "readiness_state",
            postgresql_where=text("readiness_state IN ('ready_for_uplift', 'blocked')"),
        ),
        Index(
            "ix_readiness_evaluations_first_blocker_kind",
            text("((blockers->0->>'predicate_kind'))"),
            postgresql_where=text("readiness_state = 'blocked'"),
        ),
        Index(
            "ix_readiness_evaluations_evaluated_at",
            text("evaluated_at DESC"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ReadinessEvaluation id={self.id} device={self.device_id} "
            f"state={self.readiness_state} blockers={len(self.blockers)}>"
        )
