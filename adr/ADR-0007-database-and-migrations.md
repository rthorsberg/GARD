# ADR-0007 — Database and migrations: PostgreSQL 16 + SQLAlchemy 2 + Alembic

- **Status**: Accepted
- **Date**: 2026-05-27
- **Feature**: F1 (`001-device-import-normalize`)
- **Source decision**: research.md D2
- **Constitution principle**: IV (Evidence, Audit & Explainability — NON-NEGOTIABLE)

## Context

We need a single OLTP store for application data, raw observations,
audit, and lifecycle evidence — without bringing a second datastore on
day 1. The store must support:

- Append-only constraints at the role level (audit, evidence).
- Indexable JSON for raw payloads (CSV row → JSONB → query-able).
- Partial-unique indexes (e.g., serial number when present, hostname+
  site fallback when serial is null).
- A simple, durable worker queue (`FOR UPDATE SKIP LOCKED`).

## Decision

- **Database**: PostgreSQL 16 (matching the NetBox community floor).
- **ORM / Core**: SQLAlchemy 2.0 in 2.x style (`sqlalchemy.orm.Mapped`,
  imperative cores via `select()`).
- **Migrations**: Alembic, autogenerate disabled by default — every
  migration is hand-reviewed.
- **Driver**: `psycopg[binary]` v3 (async-capable; v1 uses sync engine).

The schema is captured in `data-model.md`. Append-only enforcement
belongs to ADR-0009; this ADR only commits us to the engine.

## Consequences

- One Postgres database per environment. HA via streaming replication /
  Patroni is the operational story.
- We accept SQLAlchemy 2.0 as a hard floor; no 1.4-style legacy code is
  permitted.
- Schema changes always go through Alembic; running services never
  hand-edit DDL. CI verifies that every migration is reversible (down +
  up round-trip on a scratch DB).

## Alternatives considered

- **SQLite** — single-writer constraint blocks the worker pattern.
- **MySQL/MariaDB** — JSON ergonomics weaker than JSONB; partial indexes
  restricted.
- **CockroachDB / Yugabyte** — distributed strength irrelevant in v1;
  ops complexity not justified.

## References

- research.md §D2
- data-model.md
- ROADMAP.md (ADR-0007 reservation)
