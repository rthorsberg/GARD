"""F7: NetBox integration — device columns, sync runs, evidence type

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-31

Per specs/007-netbox-integration-read/data-model.md:

  - devices.netbox_device_id (partial unique)
  - devices.netbox_last_synced_at
  - devices.tags (TEXT[])
  - netbox_sync_runs table
  - lifecycle_evidence.evidence_type += 'netbox_sync'
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYNC_RUN_STATUSES = ("running", "completed", "failed")

_EVIDENCE_TYPES = (
    "import",
    "manual_mapping",
    "rule_override",
    "re_evaluation",
    "firmware_package_upload",
    "firmware_catalog_load",
    "netbox_sync",
)

_PREV_EVIDENCE_TYPES = tuple(t for t in _EVIDENCE_TYPES if t != "netbox_sync")


def _check_evidence(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"evidence_type IN ({quoted})"


def upgrade() -> None:
    op.add_column("devices", sa.Column("netbox_device_id", sa.Integer(), nullable=True))
    op.add_column(
        "devices",
        sa.Column("netbox_last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("devices", sa.Column("tags", pg.ARRAY(sa.String()), nullable=True))

    op.create_index(
        "uq_devices_netbox_device_id",
        "devices",
        ["netbox_device_id"],
        unique=True,
        postgresql_where=sa.text("netbox_device_id IS NOT NULL"),
    )

    op.create_table(
        "netbox_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orphaned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _SYNC_RUN_STATUSES)})",
            name="netbox_sync_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_netbox_sync_runs_started_at",
        "netbox_sync_runs",
        ["started_at"],
    )

    op.drop_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        _check_evidence(_EVIDENCE_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        _check_evidence(_PREV_EVIDENCE_TYPES),
    )

    op.drop_index("ix_netbox_sync_runs_started_at", table_name="netbox_sync_runs")
    op.drop_table("netbox_sync_runs")

    op.drop_index("uq_devices_netbox_device_id", table_name="devices")
    op.drop_column("devices", "tags")
    op.drop_column("devices", "netbox_last_synced_at")
    op.drop_column("devices", "netbox_device_id")
