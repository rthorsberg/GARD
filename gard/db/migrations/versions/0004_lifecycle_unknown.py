"""F2: extend devices.lifecycle_state CHECK to allow 'unknown'

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-29 16:50:00

Per F2 spec.md FR-010, the device lifecycle state machine adds an
``unknown`` terminal that's entered when a target matches but no
observed firmware is on file. F1's initial schema (migration 0002)
declared a CHECK constraint over a fixed value tuple that did not
include ``unknown``; we extend that tuple here.

This is a pure expand: existing rows keep their values, the new value
is additionally accepted. There is no data backfill — the F2
``compliance_controller`` is the first writer that will produce
``unknown`` rows, and only on devices that already lack an
``observed_firmware`` value.

Downgrade drops back to the F1 + F2-data tuple. Any rows already in
``unknown`` would block the downgrade (CHECK violation), so callers
must first re-map them to ``classified`` before reverting.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_STATES = (
    "imported",
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "unknown",
    "ready_for_uplift",
    "blocked",
    "uplift_planned",
    "approval_pending",
    "approved",
    "exception_approved",
)


_OLD_STATES = tuple(s for s in _NEW_STATES if s != "unknown")


def _check_clause(states: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{s}'" for s in states)
    return f"lifecycle_state IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint("ck_devices_lifecycle_state", "devices", type_="check")
    op.create_check_constraint(
        "ck_devices_lifecycle_state",
        "devices",
        _check_clause(_NEW_STATES),
    )


def downgrade() -> None:
    op.drop_constraint("ck_devices_lifecycle_state", "devices", type_="check")
    op.create_check_constraint(
        "ck_devices_lifecycle_state",
        "devices",
        _check_clause(_OLD_STATES),
    )
