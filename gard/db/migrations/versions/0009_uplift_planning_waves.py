"""F5: uplift planning & waves — plans, waves, wave_devices, exceptions

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-31

Per specs/005-uplift-planning-waves/data-model.md §1 — creates the
four F5 tables that together carry the uplift planning + exception
lifecycle:

  - uplift_plans          top-level grouping
  - uplift_waves          the reviewable batch (state machine)
  - uplift_wave_devices   the (wave, device) join with F4 snapshot
  - uplift_exceptions     operator-accepted known-risk overrides

The lifecycle invariants (ADR-0016) are enforced at three layers in
the application code; this migration installs the **DB-level** layer:

  - ck_uplift_waves_sod — approved_by ≠ drafted_by
  - ck_uplift_exceptions_sod — approved_by ≠ filed_by
  - ck_uplift_waves_terminal_consistency — terminal state requires
    a non-null <state>_at timestamp
  - ck_uplift_waves_change_window_{order,min_15m,max_24h} — the
    change-window grammar (ADR-0016 §C)
  - ck_uplift_exceptions_blocker_one_of — XOR between blocker_rule_id
    and synthetic_kind (one and only one)

Indexes are tuned for the read shapes spelled out in the F5 plan:
  - wave list filtered by (plan_id, state)
  - wave list filtered by (state, drafted_at DESC)
  - wave search by (target_platform_family, target_version)
  - exception lookup by (device_id, state)
  - lazy expiry sweep by (expires_at) WHERE state='approved'
  - one-active-exception-per-blocker uniqueness

Downgrade drops the four tables. Audit history (audit_events) is
untouched — F5's chain-of-custody record remains on the chain even
after the derived tables are dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WAVE_STATES = (
    "draft",
    "submitted",
    "approved",
    "rejected",
    "cancelled",
    "invalidated",
)

EXCEPTION_STATES = (
    "pending_review",
    "approved",
    "rejected",
    "expired",
    "withdrawn",
)

SYNTHETIC_BLOCKER_KINDS = (
    "missing_upgrade_path",
    "missing_observation_field",
)


def upgrade() -> None:
    # ---- uplift_plans -------------------------------------------------
    op.create_table(
        "uplift_plans",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 200",
            name="ck_uplift_plans_name_len",
        ),
        sa.CheckConstraint(
            "(archived_at IS NULL) = (archived_by IS NULL)",
            name="ck_uplift_plans_archived_pair",
        ),
    )
    op.create_index(
        "ix_uplift_plans_created_at_desc",
        "uplift_plans",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "uq_uplift_plans_name_active",
        "uplift_plans",
        [sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    # ---- uplift_waves -------------------------------------------------
    op.create_table(
        "uplift_waves",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("uplift_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_version", sa.String(64), nullable=False),
        sa.Column("target_platform_family", sa.String(64), nullable=False),
        sa.Column("change_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("drafted_by", sa.String(255), nullable=False),
        sa.Column(
            "drafted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("submitted_by", sa.String(255), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_citation", sa.String(2000), nullable=True),
        sa.Column("rejected_by", sa.String(255), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_citation", sa.String(2000), nullable=True),
        sa.Column("cancelled_by", sa.String(255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{v}'" for v in WAVE_STATES) + ")",
            name="ck_uplift_waves_state",
        ),
        sa.CheckConstraint(
            "change_window_end > change_window_start",
            name="ck_uplift_waves_change_window_order",
        ),
        sa.CheckConstraint(
            "change_window_end - change_window_start <= interval '24 hours'",
            name="ck_uplift_waves_change_window_max_24h",
        ),
        sa.CheckConstraint(
            "change_window_end - change_window_start >= interval '15 minutes'",
            name="ck_uplift_waves_change_window_min_15m",
        ),
        sa.CheckConstraint(
            "approval_citation IS NULL OR length(approval_citation) BETWEEN 20 AND 2000",
            name="ck_uplift_waves_approval_citation_len",
        ),
        sa.CheckConstraint(
            "rejection_citation IS NULL OR length(rejection_citation) BETWEEN 20 AND 2000",
            name="ck_uplift_waves_rejection_citation_len",
        ),
        sa.CheckConstraint(
            "cancellation_reason IS NULL OR length(cancellation_reason) BETWEEN 10 AND 500",
            name="ck_uplift_waves_cancellation_reason_len",
        ),
        # ADR-0016 §B layer 3: DB-level separation of duties.
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by <> drafted_by",
            name="ck_uplift_waves_sod",
        ),
        # ADR-0016 §A: every terminal state requires its timestamp column to be set.
        sa.CheckConstraint(
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
    )
    op.create_index(
        "ix_uplift_waves_plan_state",
        "uplift_waves",
        ["plan_id", "state"],
    )
    op.create_index(
        "ix_uplift_waves_state_drafted_at_desc",
        "uplift_waves",
        ["state", sa.text("drafted_at DESC")],
    )
    op.create_index(
        "ix_uplift_waves_target_version",
        "uplift_waves",
        ["target_platform_family", "target_version"],
    )
    op.create_index(
        "uq_uplift_waves_plan_idempotency",
        "uplift_waves",
        ["plan_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_uplift_waves_plan_name",
        "uplift_waves",
        ["plan_id", sa.text("lower(name)")],
        unique=True,
    )

    # ---- uplift_wave_devices ------------------------------------------
    op.create_table(
        "uplift_wave_devices",
        sa.Column(
            "wave_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("uplift_waves.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column(
            "readiness_evaluation_ref",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("readiness_evaluations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("snapshot_target_version", sa.String(64), nullable=True),
        sa.Column("snapshot_observed_version", sa.String(64), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("wave_id", "device_id"),
        sa.CheckConstraint("position >= 1", name="ck_uplift_wave_devices_position_pos"),
    )
    op.create_index(
        "ix_uplift_wave_devices_device",
        "uplift_wave_devices",
        ["device_id"],
    )
    op.create_index(
        "uq_uplift_wave_devices_wave_position",
        "uplift_wave_devices",
        ["wave_id", "position"],
        unique=True,
    )

    # ---- uplift_exceptions --------------------------------------------
    op.create_table(
        "uplift_exceptions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "blocker_rule_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("firmware_prerequisite_rules.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("synthetic_kind", sa.String(64), nullable=True),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending_review"),
        sa.Column("filed_by", sa.String(255), nullable=False),
        sa.Column(
            "filed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(255), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(255), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{v}'" for v in EXCEPTION_STATES) + ")",
            name="ck_uplift_exceptions_state",
        ),
        sa.CheckConstraint(
            "(blocker_rule_id IS NOT NULL)::int + (synthetic_kind IS NOT NULL)::int = 1",
            name="ck_uplift_exceptions_blocker_one_of",
        ),
        sa.CheckConstraint(
            "synthetic_kind IS NULL OR synthetic_kind IN ("
            + ", ".join(f"'{v}'" for v in SYNTHETIC_BLOCKER_KINDS)
            + ")",
            name="ck_uplift_exceptions_synthetic_kind_valid",
        ),
        sa.CheckConstraint(
            "length(justification) BETWEEN 20 AND 2000",
            name="ck_uplift_exceptions_justification_len",
        ),
        sa.CheckConstraint(
            "expires_at > filed_at",
            name="ck_uplift_exceptions_expires_after_filed",
        ),
        sa.CheckConstraint(
            "expires_at <= filed_at + interval '365 days'",
            name="ck_uplift_exceptions_max_lifetime_365d",
        ),
        # ADR-0016 §B layer 3: DB-level SoD for exception approval.
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by <> filed_by",
            name="ck_uplift_exceptions_sod",
        ),
    )
    op.create_index(
        "ix_uplift_exceptions_device_state",
        "uplift_exceptions",
        ["device_id", "state"],
    )
    op.create_index(
        "ix_uplift_exceptions_expires_at",
        "uplift_exceptions",
        ["expires_at"],
        postgresql_where=sa.text("state = 'approved'"),
    )
    op.create_index(
        "uq_uplift_exceptions_one_active_per_blocker",
        "uplift_exceptions",
        [
            "device_id",
            sa.text("coalesce(blocker_rule_id::text, synthetic_kind)"),
        ],
        unique=True,
        postgresql_where=sa.text("state = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_uplift_exceptions_one_active_per_blocker",
        table_name="uplift_exceptions",
    )
    op.drop_index("ix_uplift_exceptions_expires_at", table_name="uplift_exceptions")
    op.drop_index("ix_uplift_exceptions_device_state", table_name="uplift_exceptions")
    op.drop_table("uplift_exceptions")

    op.drop_index("uq_uplift_wave_devices_wave_position", table_name="uplift_wave_devices")
    op.drop_index("ix_uplift_wave_devices_device", table_name="uplift_wave_devices")
    op.drop_table("uplift_wave_devices")

    op.drop_index("uq_uplift_waves_plan_name", table_name="uplift_waves")
    op.drop_index("uq_uplift_waves_plan_idempotency", table_name="uplift_waves")
    op.drop_index("ix_uplift_waves_target_version", table_name="uplift_waves")
    op.drop_index("ix_uplift_waves_state_drafted_at_desc", table_name="uplift_waves")
    op.drop_index("ix_uplift_waves_plan_state", table_name="uplift_waves")
    op.drop_table("uplift_waves")

    op.drop_index("uq_uplift_plans_name_active", table_name="uplift_plans")
    op.drop_index("ix_uplift_plans_created_at_desc", table_name="uplift_plans")
    op.drop_table("uplift_plans")
