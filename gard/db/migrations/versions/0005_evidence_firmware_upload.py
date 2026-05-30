"""F2: extend lifecycle_evidence.evidence_type to allow 'firmware_package_upload'

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-30 00:55:00

Per F2 spec.md (T057 blob-upload path) the firmware-package blob
upload emits one ``LifecycleEvidence`` row of type
``firmware_package_upload`` alongside the ``firmware_catalog.package
.blob_stored`` AuditEvent. F1's initial schema declared the
evidence_type CHECK over a fixed value tuple that did not include this
new type; we extend that tuple here.

This is a pure expand: existing rows keep their values, the new value
is additionally accepted. There is no data backfill.

Downgrade drops back to the F1 tuple. Any rows already stamped
``firmware_package_upload`` would block downgrade with a CHECK
violation — operators must drop or relabel them first.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_TYPES = (
    "import",
    "manual_mapping",
    "rule_override",
    "re_evaluation",
    "firmware_package_upload",
)


_OLD_TYPES = tuple(t for t in _NEW_TYPES if t != "firmware_package_upload")


def _check(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"evidence_type IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_lifecycle_evidence_evidence_type",
        "lifecycle_evidence",
        _check(_NEW_TYPES),
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
        _check(_OLD_TYPES),
    )
