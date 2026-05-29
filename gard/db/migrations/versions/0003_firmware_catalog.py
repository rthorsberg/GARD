"""F2: firmware catalog — targets, packages, upgrade paths, prerequisites + device facts

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-29 16:30:00

Per specs/002-firmware-catalog/data-model.md §7 — applies in this order:

1. Extend ``devices`` with three optional observation columns: ``ram_mb``,
   ``disk_mb``, ``licenses``. (Enum extension that data-model.md §7 calls for
   is unnecessary in F1's layout — ``lifecycle_state`` is a CHECK-constrained
   varchar and F1 already pre-declared the F2 values in its check tuple.)
2. ``firmware_targets`` with the common columns + entity-specific shape, partial
   UNIQUE on ``name`` where ``removed_at IS NULL``.
3. ``firmware_packages`` with partial UNIQUE on ``(vendor, platform_family,
   version)`` where ``removed_at IS NULL``.
4. ``firmware_upgrade_paths`` (one row per edge).
5. ``firmware_prerequisite_rules``.
6. Indexes per data-model.md §1.

Per ADR-0011: catalog tables are written by the regular ``gard_app`` /
``gard_writer`` role (UPDATE is required for soft-delete and resurrect). The
append-only role established in F1 is **not** granted to these tables; that role
continues to own ``audit_events`` + ``lifecycle_evidence`` only.

Downgrade raises NotImplementedError — F2 data is not recoverable from F1 alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------- helpers ----------

PREDICATE_KINDS = (
    "min_ram_mb",
    "min_disk_mb",
    "min_current_version",
    "hardware_revision_in",
    "license_present",
    "intermediate_version_required",
    "not_in_state",
    "region_in",
    "tagged_with",
)
PREREQ_SEVERITIES = ("required", "recommended")
PACKAGE_VENDORS = ("cisco", "juniper", "nokia")


def _check_in(col: str, allowed: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in allowed)
    return sa.CheckConstraint(f"{col} IN ({quoted})", name=name)


# Common catalog columns (data-model.md §1 preamble).
# The return type is intentionally ``list[Any]`` rather than
# ``list[sa.Column[object]]`` because SQLAlchemy's TypeEngine generics
# don't compose cleanly with Alembic's spread-as-positional-arg form;
# narrowing is unhelpful since we never read these columns from Python.
def _common_cols() -> list[Any]:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("loaded_from_git_sha", sa.String(40), nullable=True),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_file_relpath", sa.String, nullable=False),
        sa.Column("catalog_schema_version", sa.String(16), nullable=False),
    ]


# ---------- upgrade ----------


def upgrade() -> None:
    # 1. Device facts extension --------------------------------------------------
    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("ram_mb", sa.Integer, nullable=True))
        batch.add_column(sa.Column("disk_mb", sa.Integer, nullable=True))
        batch.add_column(
            sa.Column("licenses", pg.ARRAY(sa.String), nullable=True),
        )

    # 2. firmware_targets --------------------------------------------------------
    op.create_table(
        "firmware_targets",
        *_common_cols(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("platform_family", sa.String, nullable=False),
        sa.Column("target_version", sa.String, nullable=False),
        sa.Column("scope_selector", pg.JSONB, nullable=False),
        # valid_from/until are calendar dates per data-model.md §1
        # (matches release_date on packages). DateTime adds tz semantics
        # that don't apply to policy windows.
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_until", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_firmware_targets_platform_removed",
        "firmware_targets",
        ["platform_family", "removed_at"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_firmware_targets_name_live "
        "ON firmware_targets (name) WHERE removed_at IS NULL"
    )
    op.create_index(
        "ix_firmware_targets_source_file",
        "firmware_targets",
        ["source_file_relpath"],
    )

    # 3. firmware_packages -------------------------------------------------------
    op.create_table(
        "firmware_packages",
        *_common_cols(),
        sa.Column("vendor", sa.String, nullable=False),
        sa.Column("platform_family", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("signed_by", sa.String, nullable=False),
        sa.Column("release_date", sa.Date, nullable=True),
        sa.Column("download_url", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "blob_present",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("blob_stored_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(sha256) = 64", name="firmware_package_sha256_len"),
        sa.CheckConstraint("byte_size > 0", name="firmware_package_byte_size_positive"),
        _check_in("vendor", PACKAGE_VENDORS, "firmware_package_vendor"),
    )
    op.create_index(
        "ix_firmware_packages_vendor_platform_version",
        "firmware_packages",
        ["vendor", "platform_family", "version", "removed_at"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_firmware_packages_natural_live "
        "ON firmware_packages (vendor, platform_family, version) WHERE removed_at IS NULL"
    )
    op.create_index(
        "ix_firmware_packages_source_file",
        "firmware_packages",
        ["source_file_relpath"],
    )

    # 4. firmware_upgrade_paths --------------------------------------------------
    op.create_table(
        "firmware_upgrade_paths",
        *_common_cols(),
        sa.Column("platform_family", sa.String, nullable=False),
        sa.Column("from_version", sa.String, nullable=False),
        sa.Column("to_version", sa.String, nullable=False),
        sa.Column("weight", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.CheckConstraint("weight >= 1", name="firmware_upgrade_path_weight_min"),
    )
    op.create_index(
        "ix_firmware_upgrade_paths_platform_versions",
        "firmware_upgrade_paths",
        ["platform_family", "removed_at", "from_version", "to_version"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_firmware_upgrade_paths_edge_live "
        "ON firmware_upgrade_paths (platform_family, from_version, to_version) "
        "WHERE removed_at IS NULL"
    )

    # 5. firmware_prerequisite_rules ---------------------------------------------
    op.create_table(
        "firmware_prerequisite_rules",
        *_common_cols(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("applies_to", pg.JSONB, nullable=False),
        sa.Column("predicate_kind", sa.String(64), nullable=False),
        sa.Column("predicate_args", pg.JSONB, nullable=False),
        sa.Column(
            "severity",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'required'"),
        ),
        sa.Column("evaluable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _check_in("predicate_kind", PREDICATE_KINDS, "firmware_prereq_predicate_kind"),
        _check_in("severity", PREREQ_SEVERITIES, "firmware_prereq_severity"),
    )
    op.create_index(
        "ix_firmware_prereq_kind_removed",
        "firmware_prerequisite_rules",
        ["predicate_kind", "removed_at"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_firmware_prereq_name_live "
        "ON firmware_prerequisite_rules (name) WHERE removed_at IS NULL"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade from 0003 (firmware catalog) is not supported in v1. "
        "F2 introduces new tables with no migration path back to F1's data. "
        "Restore from the pre-F2 database backup or operate forward."
    )
