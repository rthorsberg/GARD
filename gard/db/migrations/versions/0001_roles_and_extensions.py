"""Bootstrap: create DB roles and required extensions

Revision ID: 0001
Revises:
Create Date: 2026-05-27 22:30:00

ADR-0009: append-only enforcement at the role level.
- ``gard_app``: full INSERT/UPDATE/SELECT on regular tables, but UPDATE
  and DELETE are explicitly REVOKED on append-only tables (audit_events,
  device_observations, lifecycle_evidence) by migration 0002.
- ``gard_writer_append_only``: INSERT/SELECT only — used by the audit
  and evidence helpers off the request path.

Both roles are created idempotently; in CI / local docker-compose the
default ``gard`` superuser may be the owner. In production the
deployment runs:

    CREATE USER gard_app WITH LOGIN PASSWORD '...';
    CREATE USER gard_writer_append_only WITH LOGIN PASSWORD '...';
    GRANT gard_app, gard_writer_append_only TO gard;

before pointing :data:`GARD_DATABASE_URL` and
:data:`GARD_DATABASE_URL_APPEND_ONLY` at the respective accounts.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTE: CREATE ROLE cannot run inside a transaction for some pg
    # configurations; we tolerate "already exists" and run idempotently.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gard_app') THEN
                CREATE ROLE gard_app NOLOGIN;
            END IF;
            IF NOT EXISTS (
                SELECT FROM pg_roles WHERE rolname = 'gard_writer_append_only'
            ) THEN
                CREATE ROLE gard_writer_append_only NOLOGIN;
            END IF;
        END$$;
        """
    )

    # No third-party extensions in v1 (UUID7 is generated client-side).
    # Reserve a hook for `pg_uuidv7` if we ever switch.


def downgrade() -> None:
    # Roles are intentionally not dropped — they may own objects in
    # other schemas and dropping them is a deployment concern.
    pass
