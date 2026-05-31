"""F4: readiness_evaluations table for append-only readiness verdicts

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-31

Per specs/004-readiness-prerequisites/data-model.md §1.1 — creates the
`readiness_evaluations` table that holds one row per evaluation pass
whose verdict changed (R-5 idempotency). Append-only at the row level
(re-evaluations INSERT new rows; never UPDATE). The latest row per
device is the live readiness verdict.

Like F3's `compliance_evaluations`, this table lives in `gard_app` and
is written by the regular `gard_writer` role. It is a derived-state
cache that can be rebuilt from F2's prereq catalogue + F2's upgrade
graph + F3's `compliance_evaluations`. The chain-of-custody record
stays in `audit_events` (ADR-0009).

Indices:
  - `ix_readiness_evaluations_device_evaluated_desc` —
    (device_id, evaluated_at DESC) serves DISTINCT-ON latest-per-device.
  - `ix_readiness_evaluations_state` — partial on rows whose
    readiness_state is ready_for_uplift or blocked, used by the
    summary counter and the device-list endpoint.
  - `ix_readiness_evaluations_first_blocker_kind` — partial
    expression index on (blockers->0->>'predicate_kind') WHERE
    readiness_state='blocked'; supports the top-blocker-categories
    aggregate without scanning ready/not_applicable rows.
  - `ix_readiness_evaluations_evaluated_at` — supports future
    pruning + time-range debug queries.

Pruning seam matches F3 — v2 picks between time-partitioning and a
scheduled DELETE with a retention env. Choice is non-breaking against
v1 query patterns.

Downgrade drops the table. Re-runs of the controller will recreate
live rows from upstream sources; classification history is lost.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


READINESS_STATES = (
    "ready_for_uplift",
    "blocked",
    "not_applicable",
)


def upgrade() -> None:
    op.create_table(
        "readiness_evaluations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "compliance_evaluation_ref",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("compliance_evaluations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("readiness_state", sa.String(32), nullable=False),
        sa.Column("target_version", sa.String(64), nullable=True),
        sa.Column("observed_version", sa.String(64), nullable=True),
        sa.Column("upgrade_path_exists", sa.Boolean, nullable=False),
        sa.Column("applicable_rules_count", sa.Integer, nullable=False),
        sa.Column(
            "blockers",
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
        sa.Column(
            "reasons",
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
        sa.CheckConstraint(
            "readiness_state IN ("
            + ", ".join(f"'{v}'" for v in READINESS_STATES)
            + ")",
            name="ck_readiness_eval_state",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_readiness_eval_confidence_range",
        ),
        sa.CheckConstraint(
            "applicable_rules_count >= 0",
            name="ck_readiness_eval_applicable_rules_nonneg",
        ),
    )

    op.create_index(
        "ix_readiness_evaluations_device_evaluated_desc",
        "readiness_evaluations",
        ["device_id", sa.text("evaluated_at DESC")],
    )
    op.create_index(
        "ix_readiness_evaluations_state",
        "readiness_evaluations",
        ["readiness_state"],
        postgresql_where=sa.text(
            "readiness_state IN ('ready_for_uplift', 'blocked')"
        ),
    )
    op.create_index(
        "ix_readiness_evaluations_first_blocker_kind",
        "readiness_evaluations",
        [sa.text("((blockers->0->>'predicate_kind'))")],
        postgresql_where=sa.text("readiness_state = 'blocked'"),
    )
    op.create_index(
        "ix_readiness_evaluations_evaluated_at",
        "readiness_evaluations",
        [sa.text("evaluated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_readiness_evaluations_evaluated_at",
        table_name="readiness_evaluations",
    )
    op.drop_index(
        "ix_readiness_evaluations_first_blocker_kind",
        table_name="readiness_evaluations",
    )
    op.drop_index(
        "ix_readiness_evaluations_state",
        table_name="readiness_evaluations",
    )
    op.drop_index(
        "ix_readiness_evaluations_device_evaluated_desc",
        table_name="readiness_evaluations",
    )
    op.drop_table("readiness_evaluations")
