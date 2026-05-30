"""`compliance_evaluations` — append-only drift classification rows (F3).

One row per evaluation pass that changed the device's compliance
state, drift type, reasons, or recommended actions. Silent (no row,
no audit) for re-evaluations against unchanged inputs.

The latest row per device, ordered by ``evaluated_at DESC``, is the
live verdict that the REST + MCP surfaces return. Older rows are the
classification audit trail (ADR-0014 §B).

Written by the regular ``gard_writer`` role — this is a derived-state
cache, not chain-of-custody evidence; the audit chain in
``audit_events`` is the immutable record (ADR-0014, ADR-0009).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class ComplianceEvaluation(Base):
    __tablename__ = "compliance_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    target_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("firmware_targets.id", ondelete="SET NULL"), nullable=True
    )
    observation_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_observations.id", ondelete="SET NULL"), nullable=True
    )

    # Storing the F2 FirmwareComplianceState value as a string — it shares
    # the same five-value vocabulary as F2 (`outside_target`, `compliant`,
    # `unknown`, `target_defined`, `classified`) and the DB CHECK constraint
    # is the authority.
    compliance_state: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_drift_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # JSONB list of drift type strings, sorted by precedence (ADR-0014 §C).
    secondary_drift_types: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # JSONB list of ComplianceReason dicts (kind, message, ref_id?, ref_type?).
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # JSONB list of RecommendedAction dicts (kind, target_*?, requires?).
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    # 0.0..1.0; v1 always 1.0 (deterministic rules, no inference).
    confidence: Mapped[decimal.Decimal] = mapped_column(Numeric(3, 2), nullable=False)

    evaluated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Free-form actor string ("system:catalog_reload", "user:alice@example.com").
    actor: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index(
            "ix_compliance_evaluations_device_evaluated_desc",
            "device_id",
            text("evaluated_at DESC"),
        ),
        Index(
            "ix_compliance_evaluations_primary_drift_type",
            "primary_drift_type",
            postgresql_where=text("primary_drift_type IS NOT NULL"),
        ),
        Index(
            "ix_compliance_evaluations_evaluated_at",
            text("evaluated_at DESC"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ComplianceEvaluation id={self.id} device={self.device_id} "
            f"state={self.compliance_state} primary={self.primary_drift_type}>"
        )
