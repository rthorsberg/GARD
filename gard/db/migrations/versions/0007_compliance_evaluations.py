"""F3: compliance_evaluations table for append-only drift classification

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-30 14:30:00

Per specs/003-compliance-drift-evaluation/data-model.md §1 — creates
the `compliance_evaluations` table that holds one row per evaluation
pass that resulted in a state-or-drift transition. Append-only at the
row level (re-evaluations INSERT new rows; never UPDATE). The latest
row per device is the live verdict; older rows are the classification
audit trail (ADR-0014 §B).

The table lives in the standard `gard_app` schema and is written by
the regular `gard_writer` role — NOT the append-only audit role. This
is intentional: `compliance_evaluations` is a derived-state cache,
not chain-of-custody evidence. The cache can be rebuilt by re-running
`compliance_evaluation_controller.evaluate_many()`; the audit chain
in `audit_events` is the immutable record.

Indices:
  - `ix_compliance_evaluations_device_evaluated_desc` —
    (device_id, evaluated_at DESC) serves the DISTINCT ON
    latest-per-device query used by the summary + listing endpoints.
  - `ix_compliance_evaluations_primary_drift_type` —
    partial index on (primary_drift_type) WHERE NOT NULL, drives
    the summary counter group-by without scanning compliant rows.
  - `ix_compliance_evaluations_evaluated_at` — supports future
    pruning + time-range debug queries.

Pruning seam: the table grows linearly (v1 estimate ~18 M rows/year
at 5,000 devices x 10 evaluations/day). v2 will pick between
time-partitioned tables (`compliance_evaluations_YYYYMM`) or a
scheduled DELETE with `GARD_EVALUATION_RETENTION_DAYS`. Either choice
is non-breaking against the v1 query patterns.

Downgrade drops the table. Re-runs of the controller will recreate
the live rows from upstream sources; classification history is lost.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


COMPLIANCE_STATES = (
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "unknown",
)

DRIFT_TYPES = (
    "target_drift",
    "catalog_drift",
    "package_drift",
    "rule_drift",
    "evidence_drift",
    "discovery_drift",
    "exception_drift",
)


def _check_in(col: str, allowed: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in allowed)
    return sa.CheckConstraint(f"{col} IN ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "compliance_evaluations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_ref",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("firmware_targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "observation_ref",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("device_observations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("compliance_state", sa.String(32), nullable=False),
        sa.Column("primary_drift_type", sa.String(32), nullable=True),
        sa.Column(
            "secondary_drift_types",
            pg.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("target_version", sa.String(64), nullable=True),
        sa.Column("observed_version", sa.String(64), nullable=True),
        sa.Column(
            "reasons",
            pg.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "recommended_actions",
            pg.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        _check_in("compliance_state", COMPLIANCE_STATES, "ck_compliance_eval_state"),
        sa.CheckConstraint(
            "primary_drift_type IS NULL "
            "OR primary_drift_type IN (" + ", ".join(f"'{v}'" for v in DRIFT_TYPES) + ")",
            name="ck_compliance_eval_primary_drift",
        ),
        sa.CheckConstraint(
            # Compliant <=> no primary drift. The biconditional is the F3
            # invariant: if you're compliant, there is no drift type to
            # surface; if there's a drift type, you are NOT compliant.
            "(primary_drift_type IS NULL) = (compliance_state = 'compliant')",
            name="ck_compliance_eval_compliant_iff_no_drift",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_compliance_eval_confidence_range",
        ),
    )

    op.create_index(
        "ix_compliance_evaluations_device_evaluated_desc",
        "compliance_evaluations",
        ["device_id", sa.text("evaluated_at DESC")],
    )
    # Partial index — only non-compliant rows participate in the summary
    # counter group-by, so we skip compliant rows entirely.
    op.create_index(
        "ix_compliance_evaluations_primary_drift_type",
        "compliance_evaluations",
        ["primary_drift_type"],
        postgresql_where=sa.text("primary_drift_type IS NOT NULL"),
    )
    op.create_index(
        "ix_compliance_evaluations_evaluated_at",
        "compliance_evaluations",
        [sa.text("evaluated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_evaluations_evaluated_at",
        table_name="compliance_evaluations",
    )
    op.drop_index(
        "ix_compliance_evaluations_primary_drift_type",
        table_name="compliance_evaluations",
    )
    op.drop_index(
        "ix_compliance_evaluations_device_evaluated_desc",
        table_name="compliance_evaluations",
    )
    op.drop_table("compliance_evaluations")
