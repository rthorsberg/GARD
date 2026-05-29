"""F2: extend lifecycle_evidence.evidence_type to allow 'firmware_catalog_load'

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-30 01:05:00

Per F2 spec.md (T059 chain-of-custody) the firmware-catalog
controller emits one ``LifecycleEvidence`` row per reload pass with
``evidence_type = 'firmware_catalog_load'`` and a Merkle-style
``source_checksum`` over the sorted list of loaded git SHAs. The F1
CHECK constraint must accept the new value.

This is a pure expand on top of 0005 (which added
``firmware_package_upload``). Existing rows keep their values.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_TYPES = (
    "import",
    "manual_mapping",
    "rule_override",
    "re_evaluation",
    "firmware_package_upload",
    "firmware_catalog_load",
)

_OLD_TYPES = tuple(t for t in _NEW_TYPES if t != "firmware_catalog_load")


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
