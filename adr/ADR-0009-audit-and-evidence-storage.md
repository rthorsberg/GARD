# ADR-0009 — Audit and evidence storage: Postgres tables, role-enforced append-only, daily checksum chain

- **Status**: Accepted
- **Date**: 2026-05-27
- **Feature**: F1 (`001-device-import-normalize`)
- **Source decision**: research.md D4
- **Constitution principle**: IV (Evidence, Audit & Explainability — NON-NEGOTIABLE)

## Context

The constitution treats audit and lifecycle evidence as
non-negotiable: every state-changing action emits an `AuditEvent`, and
every lifecycle-relevant transition emits a `LifecycleEvidence` row.
Both must be **append-only** and **tamper-evident**. v1 must achieve
this without dragging in object storage with WORM, Kafka, or a separate
audit DB.

## Decision

- Both `audit_events` and `lifecycle_evidence` are **Postgres tables**
  in the same database as the application.
- Append-only enforcement is implemented at the **DB role level**:
  - `gard_app` — has `INSERT, SELECT` on these tables; `UPDATE`
    and `DELETE` are revoked by the migration.
  - `gard_writer_append_only` — also has `INSERT, SELECT` only
    (used by the worker for evidence emission off the request path).
  - No application role has `UPDATE` or `DELETE`. The only way to
    rewrite history is via DDL by a DBA — and that's the audit point.
- Each row carries a **`row_hash`**: SHA-256 of canonical JSON of the
  row (excluding `row_hash` itself), computed by the application before
  insert.
- A **daily checksum-chain job** (run by `gard.worker`) seals the
  previous UTC day's rows by chaining their `row_hash`es into a single
  `last_event_hash`, stored in `audit_chain_heads(day, last_event_hash,
  sealed_at)`. Tampering with any past row breaks the chain.

## Schema (sketch)

| Table | Append-only | Index strategy |
|---|---|---|
| `audit_events` | yes | `(timestamp DESC, id)`, `(correlation_id)`, GIN on `details` |
| `lifecycle_evidence` | yes | `(subject_id, timestamp DESC)`, `(evidence_type)`, GIN on `payload` |
| `audit_chain_heads` | yes | `PRIMARY KEY (day)` |

## Consequences

- One Postgres deployable; HA story is the same as the application
  database.
- The chain seals only sealed days; today's window remains mutable up
  to its `row_hash` — an attacker who deletes a row from today before
  midnight UTC defeats the chain for that day. Mitigations: per-row
  hashes are still in place; we accept this and document it as the
  boundary of the v1 guarantee. v2 promotes evidence to S3-with-
  Object-Lock for stronger guarantees.
- Schema and field names match the security spec verbatim, so v2 can
  migrate to a separate audit DB / object store with no domain-model
  change.

## Alternatives considered

- **Separate audit Postgres instance** — premature. Documented as the
  promotion path: split connection string, then split the database.
- **Append-only object storage (S3 Object Lock / WORM)** — stronger
  guarantee, external dependency in v1.
- **Kafka / Redpanda event store** — overkill for v1 volumes.

## References

- research.md §D4
- spec.md FR-021, FR-022, SC-007
- data-model.md §`audit_events`, §`lifecycle_evidence`,
  §`audit_chain_heads`
- ROADMAP.md (ADR-0009 reservation)
