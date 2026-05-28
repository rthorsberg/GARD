"""Initial schema for F1: devices, observations, rules, mappings, jobs, audit, evidence, tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-27 22:35:00

This migration consolidates tasks.md T015..T022 into a single revision.
The end-state schema is identical to the per-entity migrations the
tasks file proposes; consolidation keeps the bootstrap deterministic
and the up/down round-trip cheap to test.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------- helpers ----------

LIFECYCLE_STATES = (
    "imported",
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "ready_for_uplift",
    "blocked",
    "uplift_planned",
    "approval_pending",
    "approved",
    "exception_approved",
)
CONFIDENCE_VALUES = ("exact", "high", "medium", "low", "manual_review_required")
RULE_SOURCES = ("file", "db")
IMPORT_STATUSES = ("pending", "processing", "completed", "failed", "cancelled")
ACTOR_TYPES = ("user", "system", "mcp_client", "adapter")
AUDIT_RESULTS = ("success", "failure", "denied")
EVIDENCE_TYPES = ("import", "manual_mapping", "rule_override", "re_evaluation")


def _check_in(col: str, allowed: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in allowed)
    return sa.CheckConstraint(f"{col} IN ({quoted})", name=name)


# ---------- upgrade ----------


def upgrade() -> None:
    # devices ----------------------------------------------------------------
    op.create_table(
        "devices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("serial_number", sa.String, nullable=True),
        sa.Column("hostname", sa.String, nullable=False),
        sa.Column("site", sa.String, nullable=False),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("role", sa.String, nullable=True),
        sa.Column("management_ip", pg.INET, nullable=True),
        sa.Column("vendor_raw", sa.String, nullable=False),
        sa.Column("vendor_normalized", sa.String, nullable=True),
        sa.Column("model_raw", sa.String, nullable=False),
        sa.Column("model_normalized", sa.String, nullable=True),
        sa.Column("platform_family", sa.String, nullable=True),
        sa.Column("hardware_revision", sa.String, nullable=True),
        sa.Column("source_system", sa.String, nullable=False),
        sa.Column(
            "lifecycle_state",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'imported'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "serial_number IS NOT NULL OR (hostname IS NOT NULL AND site IS NOT NULL)",
            name="ck_devices_device_identity_present",
        ),
        sa.CheckConstraint(
            "length(vendor_raw) > 0 OR length(model_raw) > 0",
            name="ck_devices_device_vendor_or_model_present",
        ),
        _check_in("lifecycle_state", LIFECYCLE_STATES, "ck_devices_lifecycle_state"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_devices_serial_lower ON devices (lower(serial_number)) "
        "WHERE serial_number IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_devices_hostname_site_lower "
        "ON devices (lower(hostname), lower(site)) WHERE serial_number IS NULL"
    )
    op.create_index("ix_devices_vendor_model", "devices", ["vendor_normalized", "model_normalized"])
    op.create_index("ix_devices_lifecycle_state", "devices", ["lifecycle_state"])

    # import_jobs ------------------------------------------------------------
    op.create_table(
        "import_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("row_count_total", sa.Integer, nullable=True),
        sa.Column("row_count_accepted", sa.Integer, nullable=True),
        sa.Column("row_count_rejected", sa.Integer, nullable=True),
        sa.Column("row_count_manual_review", sa.Integer, nullable=True),
        sa.Column("row_count_duplicate", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_report", pg.JSONB, nullable=True),
        sa.Column("summary", pg.JSONB, nullable=True),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column(
            "is_override",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        _check_in("status", IMPORT_STATUSES, "ck_import_jobs_status"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_import_jobs_file_sha256 ON import_jobs (file_sha256) "
        "WHERE is_override = false"
    )
    op.create_index("ix_import_jobs_status_created", "import_jobs", ["status", "created_at"])

    # device_observations ---------------------------------------------------
    op.create_table(
        "device_observations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "device_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "import_job_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("import_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("observed_firmware", sa.String, nullable=True),
        sa.Column("observed_bootloader", sa.String, nullable=True),
        sa.Column("observed_hardware_revision", sa.String, nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_by", sa.String, nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("confidence_source", sa.String, nullable=True),
        sa.Column("raw_payload", pg.JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        _check_in("confidence", CONFIDENCE_VALUES, "ck_device_observations_confidence"),
    )
    op.create_index(
        "ix_device_observations_device_created",
        "device_observations",
        ["device_id", "created_at"],
    )
    op.create_index("ix_device_observations_confidence", "device_observations", ["confidence"])
    op.execute(
        "CREATE INDEX ix_device_observations_raw_payload_gin ON device_observations "
        "USING gin (raw_payload jsonb_path_ops)"
    )

    # normalization_rules ---------------------------------------------------
    op.create_table(
        "normalization_rules",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("match", pg.JSONB, nullable=False),
        sa.Column("output", pg.JSONB, nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("source_path", sa.String, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        _check_in("confidence", ("exact", "high", "medium"), "ck_normalization_rules_confidence"),
        _check_in("source", RULE_SOURCES, "ck_normalization_rules_source"),
    )

    # manual_mappings -------------------------------------------------------
    op.create_table(
        "manual_mappings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "observation_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("device_observations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("vendor_normalized", sa.String, nullable=False),
        sa.Column("model_normalized", sa.String, nullable=False),
        sa.Column("platform_family", sa.String, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("observation_id", name="uq_manual_mappings_observation"),
    )

    # audit_events + audit_chain_heads --------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("before", pg.JSONB, nullable=True),
        sa.Column("after", pg.JSONB, nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("source_ip", pg.INET, nullable=True),
        sa.Column("row_hash", sa.Text, nullable=False),
        _check_in("actor_type", ACTOR_TYPES, "ck_audit_events_actor_type"),
        _check_in("result", AUDIT_RESULTS, "ck_audit_events_result"),
    )
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index(
        "ix_audit_events_object", "audit_events", ["object_type", "object_id", "timestamp"]
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_actor_timestamp", "audit_events", ["actor", "timestamp"])

    op.create_table(
        "audit_chain_heads",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("last_event_hash", sa.Text, nullable=False),
        sa.Column(
            "sealed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # lifecycle_evidence ----------------------------------------------------
    op.create_table(
        "lifecycle_evidence",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("before_state", pg.JSONB, nullable=True),
        sa.Column("after_state", pg.JSONB, nullable=True),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("system", sa.String, nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source_checksum", sa.String(128), nullable=True),
        sa.Column("references", pg.JSONB, nullable=True),
        sa.Column("row_hash", sa.Text, nullable=False),
        _check_in("evidence_type", EVIDENCE_TYPES, "ck_lifecycle_evidence_evidence_type"),
    )
    op.create_index(
        "ix_lifecycle_evidence_subject",
        "lifecycle_evidence",
        ["subject_type", "subject_id", "timestamp"],
    )
    op.create_index("ix_lifecycle_evidence_type", "lifecycle_evidence", ["evidence_type"])
    op.create_index("ix_lifecycle_evidence_timestamp", "lifecycle_evidence", ["timestamp"])

    # api_tokens ------------------------------------------------------------
    op.create_table(
        "api_tokens",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("subject", sa.String, nullable=False),
        sa.Column("roles", pg.ARRAY(sa.String), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String, nullable=False),
    )

    # ---------- Append-only grants (ADR-0009) ------------------------------
    # Both gard_app and gard_writer_append_only get INSERT/SELECT only on
    # audit_events, lifecycle_evidence, and device_observations.
    for tbl in ("audit_events", "lifecycle_evidence", "device_observations"):
        op.execute(f"GRANT SELECT, INSERT ON TABLE {tbl} TO gard_app")
        op.execute(f"GRANT SELECT, INSERT ON TABLE {tbl} TO gard_writer_append_only")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {tbl} FROM gard_app")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {tbl} FROM gard_writer_append_only")

    # All other tables: gard_app gets full DML, gard_writer_append_only gets
    # SELECT + INSERT (it's a writer for append-only data).
    other_tables = (
        "devices",
        "import_jobs",
        "normalization_rules",
        "manual_mappings",
        "audit_chain_heads",
        "api_tokens",
    )
    for tbl in other_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO gard_app")
        op.execute(f"GRANT SELECT ON TABLE {tbl} TO gard_writer_append_only")


def downgrade() -> None:
    for tbl in (
        "api_tokens",
        "lifecycle_evidence",
        "audit_chain_heads",
        "audit_events",
        "manual_mappings",
        "normalization_rules",
        "device_observations",
        "import_jobs",
        "devices",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
