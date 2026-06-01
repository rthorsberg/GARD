"""F10: NetBox write-back counts on sync runs and devices

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("netbox_last_writeback_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "netbox_sync_runs",
        sa.Column("writeback_updated_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "netbox_sync_runs",
        sa.Column("writeback_conflict_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "netbox_sync_runs",
        sa.Column("writeback_failed_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "netbox_sync_runs",
        sa.Column("writeback_phase", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("netbox_sync_runs", "writeback_phase")
    op.drop_column("netbox_sync_runs", "writeback_failed_count")
    op.drop_column("netbox_sync_runs", "writeback_conflict_count")
    op.drop_column("netbox_sync_runs", "writeback_updated_count")
    op.drop_column("devices", "netbox_last_writeback_at")
