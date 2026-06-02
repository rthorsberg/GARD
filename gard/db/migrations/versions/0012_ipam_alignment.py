"""F12: IPAM alignment tables and device cache columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALIGNMENT_RUN_STATUSES = ("completed", "partial", "failed", "skipped")
_FINDING_SEVERITIES = ("error", "warning", "info")
_FINDING_STATUSES = ("open", "pass")
_FINDING_KINDS = (
    "mgmt_ip_match",
    "mgmt_ip_mismatch",
    "mgmt_ip_missing_in_netbox",
    "mgmt_ip_missing_in_gard",
    "mgmt_ip_ambiguous",
    "mgmt_ip_fallback_used",
    "interface_ip_bound",
    "interface_missing_address",
    "prefix_vrf_scope_mismatch",
    "cross_device_address_conflict",
    "shared_address",
    "vrf_mismatch",
    "vrf_orphaned_in_site",
    "access_vlan_missing",
    "vlan_out_of_scope",
    "vlan_aligned",
    "overlay_rt_aligned",
    "rt_missing_on_interface",
    "rt_import_missing",
    "rt_export_missing",
    "l2vpn_module_unavailable",
)

_EVIDENCE_TYPES = (
    "import",
    "manual_mapping",
    "rule_override",
    "re_evaluation",
    "firmware_package_upload",
    "firmware_catalog_load",
    "netbox_sync",
    "netbox_ipam_alignment",
)


def _check_evidence(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"evidence_type IN ({quoted})"


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("netbox_last_alignment_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("netbox_alignment_status", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "ipam_alignment_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("netbox_sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("devices_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("findings_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("findings_warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("findings_info_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("l2vpn_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _ALIGNMENT_RUN_STATUSES)})",
            name="ipam_alignment_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["netbox_sync_run_id"],
            ["netbox_sync_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("netbox_sync_run_id"),
    )
    op.create_index(
        "ix_ipam_alignment_runs_started_at",
        "ipam_alignment_runs",
        ["started_at"],
    )

    op.create_table(
        "ipam_alignment_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("netbox_observed", pg.JSONB(), nullable=True),
        sa.Column("gard_observed", pg.JSONB(), nullable=True),
        sa.Column("remediation_hint", sa.Text(), nullable=True),
        sa.Column("interface_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"severity IN ({', '.join(repr(s) for s in _FINDING_SEVERITIES)})",
            name="ipam_alignment_findings_severity",
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _FINDING_STATUSES)})",
            name="ipam_alignment_findings_status",
        ),
        sa.CheckConstraint(
            f"kind IN ({', '.join(repr(k) for k in _FINDING_KINDS)})",
            name="ipam_alignment_findings_kind",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["ipam_alignment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ipam_alignment_findings_run_device",
        "ipam_alignment_findings",
        ["run_id", "device_id"],
    )
    op.create_index(
        "ix_ipam_alignment_findings_device_created",
        "ipam_alignment_findings",
        ["device_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_ipam_alignment_findings_open_kind",
        "ipam_alignment_findings",
        ["kind"],
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "device_network_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("netbox_device_id", sa.Integer(), nullable=False),
        sa.Column("primary_ip4", sa.String(length=64), nullable=True),
        sa.Column("primary_ip6", sa.String(length=64), nullable=True),
        sa.Column("resolved_mgmt_ip", sa.String(length=64), nullable=True),
        sa.Column("mgmt_resolution_method", sa.String(length=64), nullable=True),
        sa.Column("interfaces", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("overlay_bindings", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ipam_alignment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_network_contexts_device_captured",
        "device_network_contexts",
        ["device_id", sa.text("captured_at DESC")],
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
    prev = tuple(t for t in _EVIDENCE_TYPES if t != "netbox_ipam_alignment")
    op.create_check_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        _check_evidence(prev),
    )

    op.drop_index("ix_device_network_contexts_device_captured", "device_network_contexts")
    op.drop_table("device_network_contexts")
    op.drop_index("ix_ipam_alignment_findings_open_kind", "ipam_alignment_findings")
    op.drop_index("ix_ipam_alignment_findings_device_created", "ipam_alignment_findings")
    op.drop_index("ix_ipam_alignment_findings_run_device", "ipam_alignment_findings")
    op.drop_table("ipam_alignment_findings")
    op.drop_index("ix_ipam_alignment_runs_started_at", "ipam_alignment_runs")
    op.drop_table("ipam_alignment_runs")
    op.drop_column("devices", "netbox_alignment_status")
    op.drop_column("devices", "netbox_last_alignment_at")
