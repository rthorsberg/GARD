# Research & Binding Decisions: Firmware Catalog

**Feature**: 002-firmware-catalog
**Date**: 2026-05-29
**Status**: Approved (pre-implementation)

This document records the binding technology and design decisions made before Phase 1 design. Each decision is numbered (D1…D8 for net-new, R-1…R-9 for revisited / context-only) and references the spec assumption or functional requirement it satisfies. Anything not pinned here can shift during implementation; anything pinned here changes only via amendment of this file (or an ADR supersession).

## D1. Catalog YAML schema versioning and precedence

**Decision**: All four catalog entity kinds use JSON Schema 2020-12 with a top-level `catalog_schema_version` field (semver). v1 is `1.0.0`. The schemas live in `specs/002-firmware-catalog/contracts/*.schema.yaml` and a copy in `gard/catalog/schemas/` is the runtime validator source. Precedence between disk-loaded YAML and any runtime override is **disk-only** — no DB override layer in v1.

**Rationale**: F1's normalization catalog has a DB-override layer (Manual mapping → DB override → File rule). For firmware, an in-app override layer would directly contradict the user's locked scope decision "approval = merged PR". One catalog, one source.

**Alternatives considered**:

- Mirror F1's three-tier resolution (manual → DB → file). Rejected: re-introduces in-app authoring through the back door.
- Use a single combined-catalog YAML per platform-family. Rejected: encourages monolithic files, breaks `git blame` granularity, and conflates entity kinds.
- Use TOML instead of YAML. Rejected: YAML matches F1's normalization catalog; consistency wins over a small parser-quality argument.

**Codified by**: ADR-0011.

## D2. Git SHA capture and "what counts as approved"

**Decision**: The loader anchors each loaded row to the **file's most recent commit SHA**, obtained via the equivalent of `git log -1 --format=%H -- <relpath>`. Worktrees with uncommitted edits to a catalog file MAY still load it but **MUST** write `loaded_from_git_sha = NULL` and emit an `AuditEvent` carrying `after.dirty = true`. In `GARD_ENV=prod` the loader refuses dirty loads entirely (returns non-zero, no DB mutation).

**Rationale**: This makes the audit chain auditable in production while preserving developer ergonomics locally. The `dirty=true` warning also surfaces accidental hot-loads in dev.

**Alternatives considered**:

- Anchor to the worktree HEAD SHA. Rejected: a single bulk reload would tag unrelated files with the same SHA, defeating the per-file precision the audit story needs.
- Compute a content hash of the file instead of using a git SHA. Rejected: doesn't tie back to review history; auditors can't walk from the audit row to a PR.

**Codified by**: ADR-0011 §2.

## D3. Soft-delete vs hard-delete for catalog rows

**Decision**: Soft-delete. Rows gain a nullable `removed_at TIMESTAMP` column. The API filters `removed_at IS NULL`. Removed rows stay in the table forever (no GC in v1). Re-introducing a YAML file with identical natural key resurrects the row by setting `removed_at = NULL` and updating `loaded_from_git_sha` + `loaded_at`. This was the open question carried from the spec; it's now closed.

**Rationale**: Three reasons. (1) Audit chain walkability: `AuditEvent.after.firmware_target_id` can always be dereferenced. (2) Compliance history: a device's old `target_ref` can be resolved back to a row even after the policy is withdrawn. (3) Simpler reconciliation: re-adding a YAML is "set removed_at = NULL" instead of "INSERT and pray about FK orphans".

**Alternatives considered**:

- Hard-delete with `ON DELETE SET NULL` everywhere. Rejected: cascades the unknown into the device state machine in ugly ways, and an auditor reading the old audit row has to do an external archive lookup.
- Tombstone in a separate `firmware_targets_removed` table. Rejected: doubles the schema for marginal benefit; the `removed_at IS NULL` filter is one WHERE clause.

**Codified by**: data-model.md §1.1; spec.md Assumptions resolved.

## D4. Upgrade-path graph algorithm and library

**Decision**: Use `networkx` ≥ 3.2 for the upgrade-path graph. Construct an in-process `DiGraph` per platform family at load time, cache it under a `dict[platform_family, DiGraph]` on the controller. Reload invalidates the cache. Shortest-path queries call `networkx.shortest_path(G, source, target, weight="weight")` (Dijkstra-equivalent for non-negative weights).

**Rationale**: We need a graph traversal more than we need to write one. `networkx` is mature, has zero runtime deps beyond the stdlib, ships pure-Python wheels (no compilation surprises in Docker), and is liberally licensed. The performance budget (SC-006: < 50 ms p95 over 500 edges × 200 platforms) is met with several orders of magnitude of headroom by a Python Dijkstra implementation.

**Alternatives considered**:

- Hand-roll Dijkstra in `core/upgrade_path_graph.py`. Rejected: ~30 lines of code plus correctness-test surface, against zero saved dependencies (networkx is small and stable).
- Use a Postgres recursive CTE. Rejected: shifts complexity to SQL where it's harder to test; for adversarial cycle inputs the recursion-limit story is murky.
- Use `python-igraph`. Rejected: C-extension complicates the build; networkx is enough.

## D5. BlobStore protocol and the single v1 backend

**Decision**: Define a `BlobStore` protocol with five methods: `put(key, stream, expected_sha256) -> WriteReceipt`, `get(key) -> StreamWithVerify`, `exists(key) -> bool`, `delete(key) -> None`, `iter_keys() -> Iterator[str]`. One concrete implementation in v1: `LocalFsBlobStore` rooted at `GARD_BLOB_ROOT`. Keys are content-addressed (`sha256/<first-2-hex>/<remaining-62-hex>`) to amortize directory size. The protocol is what FastAPI dependency injection resolves; the implementation choice lives in `settings.py`.

**Rationale**: The spec retracts F1 D2 (no object store) for firmware blobs **only**. The protocol abstraction is what makes a future S3 backend a 1-day follow-up rather than a refactor through the whole catalog. Content-addressed keys mean concurrent uploads to the same package converge on the same path and the FS itself becomes the serialisation point.

**Alternatives considered**:

- Use the existing Postgres BLOB / large-object API. Rejected: Postgres LO objects are awkward to back up, complicate replication, and tying the blob to the row's lifecycle hurts the audit story (we want the blob even after a soft-delete).
- Mount cloud storage (S3 / GCS) directly in v1. Rejected: introduces a credential surface and a network path; explicitly out of v1 per the spec.
- Store blobs *inside* the YAML (base64). Rejected (and slightly absurd): GB-class binaries in YAML defeat git, defeat review, and inflate repo size.

**Codified by**: data-model.md §2; ADR-0011 §5.

## D6. Per-upload size cap and streaming policy

**Decision**: Hard cap = **5 GiB** (5 × 2^30 bytes, configurable via `GARD_FIRMWARE_BLOB_MAX_BYTES`). Uploads are streamed through Starlette's `UploadFile.read(chunk_size)` in 8 MiB chunks; SHA-256 is computed incrementally with `hashlib.sha256().update()`; on cap-exceeded the handler drains the rest of the request stream to the configured limit then returns HTTP 413. Reads are similarly streamed with chunked SHA recomputation.

**Rationale**: 5 GiB covers every realistic vendor image (Cisco IOS XR ~2.5 GB, Juniper Junos ~1.5 GB, NSO packages ~3 GB) with headroom. Chunked SHA on both write and read is what the Constitution §Security clause requires (package integrity verified). 8 MiB chunks are big enough that hash-bookkeeping overhead is negligible, small enough that worst-case memory is bounded.

**Alternatives considered**:

- No cap, "let the disk fill". Rejected: hostile-client DoS vector.
- 1 GiB cap. Rejected: too tight for IOS XR; would force a config bump on day one.
- Buffer-to-memory, hash, then write to disk. Rejected: 5 GiB into Python memory is absurd; streamed is the only sane approach.

## D7. CSV schema bump and back-compat policy

**Decision**: Bump `csv_schema_version` from `1.0.0` to `1.1.0`. Add three optional columns: `ram_mb` (integer), `disk_mb` (integer), `licenses` (semicolon-separated list — chosen over comma to avoid CSV-quoting hell). v1.0.0 CSVs continue to load without changes (additive minor bump). The CSV schema YAML in `specs/001-device-import-normalize/contracts/csv-schema.yaml` will receive an additive amendment as part of F2; the F1 contract test stays green.

**Rationale**: Back-compat for catalog contracts is non-negotiable per the constitution's "schema-breaking changes ship with a migration note and a version bump" — and the easier path is to make it not schema-breaking in the first place.

**Alternatives considered**:

- A separate F2-only ingest channel (e.g. `PUT /api/v1/devices/{id}/facts`). Rejected: introduces a second mutation surface for the same model when CSV is already the canonical path.
- Comma-separated licenses. Rejected: requires either RFC 4180 quoting (operators get this wrong) or a column-renaming hack.

**Codified by**: contracts/rest-openapi.yaml (CSV is part of F1's spec; F2 amends it).

## D8. Lifecycle state machine extension

**Decision**: Add three new values to the `LifecycleState` enum: `target_defined`, `compliant`, `outside_target`. Transitions:

```
classified ─[catalog has matching target]──▶ target_defined
target_defined ─[observed_firmware == target_version]──▶ compliant
target_defined ─[observed_firmware != target_version]──▶ outside_target
target_defined ─[observed_firmware is NULL]──▶ target_defined  (no transition; envelope reports unknown)

{compliant, outside_target} ─[observed_firmware changes]──▶ recompute via target_defined
{target_defined, compliant, outside_target} ─[matching target removed]──▶ classified
```

The transition is **owned by `compliance_controller.evaluate(device_id)`** and is the only writer of these three new states. It runs:

1. After CSV import accepts/updates a device (synchronously, in the same transaction as F1's existing rule-match step).
2. After a successful `firmware_catalog_controller.reload()` for every device whose `target_ref` might have changed (bounded — we don't re-evaluate the world, we re-evaluate only the affected scope-selector matches).
3. On demand when `GET /api/v1/devices/{id}/firmware-compliance` is called for a device whose materialised compliance is older than the most recent loader pass.

F3 will *enrich* the `outside_target` envelope with drift taxonomy but **MUST NOT** add new states or change transition rules.

**Rationale**: Adding states to F1's enum (rather than introducing a parallel `compliance_state` column) keeps the constitutional "one lifecycle, all explainable" invariant intact. The controller is the only writer, satisfying Principle II.

**Alternatives considered**:

- Compute compliance at read time and never persist. Rejected: defeats audit emission (Principle V requires an `AuditEvent` per evaluation; we can't emit at read time and not pollute the audit log with phantom evaluations).
- Use a separate `device_compliance` table. Rejected: F3 will want to attach drift fields; better to extend the existing state machine in place than create a second one that has to be reconciled.
- Make the lifecycle state machine a graph in code that asserts allowed transitions. Considered. Deferred to F3 — the v1 transition set is small enough that asserting it in the controller is fine.

**Codified by**: data-model.md §3.

---

## Revisited / context-only items (R-1…R-9)

The following are not new decisions; they document where F2 *reuses* or *bounds* F1 choices so the next reviewer doesn't have to re-derive them.

### R-1. Language, framework, ORM (D1 of F1)

Continues Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic. F2 adds one third-party dependency (`networkx`). No new vendor SDKs.

### R-2. Database choice (D2 of F1)

Continues PostgreSQL 16. F2 adds four tables (`firmware_targets`, `firmware_packages`, `firmware_upgrade_paths`, `firmware_prerequisite_rules`) and one enum extension. No new schema. No new role. The `gard_writer_append_only` role established in F1 is unchanged and continues to be the role that writes audit_events + lifecycle_evidence.

### R-3. Auth and RBAC (D3 of F1)

Continues OIDC + GARD-issued JWT. F2 adds two permissions:

- `READ_FIRMWARE_CATALOG` (default-granted to viewer, lifecycle_manager, mcp_client, system_admin)
- `MANAGE_FIRMWARE_BLOB` (granted to lifecycle_manager, system_admin)

No `MANAGE_FIRMWARE_CATALOG` permission — catalog mutation is git, not a role. This is the constitutional reading of Principle IV at full strength.

### R-4. Audit + Evidence storage (D4 of F1)

Continues append-only DB roles + daily SHA-256 chain. F2 adds new `AuditEvent.action` values under the `firmware_catalog.*` and `firmware_target.*` namespaces; emits `LifecycleEvidence` for blob upload. No schema migration on audit / evidence tables.

### R-5. MCP transport (D8 of F1)

Continues Streamable HTTP through the official Python SDK. No stdio in F2. The five new tools register on the existing server.

### R-6. F1 D2 retraction scope (NEW)

F1's research.md D2 said "no object store in v1". F2 retracts that **for firmware package blobs only**. The retraction is bounded:

- Scope of retraction: `FirmwarePackage` artefacts and only those.
- Blob storage MUST NOT be used for evidence, audit, normalization rule artefacts, MCP session storage, or any other purpose in v1.
- The `BlobStore` protocol is private to `gard.core.blob_store`; it is not exposed via any public API.
- A future S3 backend is explicitly out of scope but is what the protocol shape enables.

This is the only D-revisited entry; F1 D1, D3, D4, D5, D6, D7, D8, D9, D10 are all intact.

### R-7. Approval model (NEW design pressure test)

We considered allowing an in-app catalog edit surface (an `Approver` role pushing changes back to YAML via a git-add tool inside the API). Rejected because:

- It introduces an authorization seam the constitution doesn't have a vocabulary for (who "owns" the YAML if the API can also edit it?).
- It complicates the audit story (two paths to a catalog change, only one of which has a PR).
- The user explicitly chose "git-native" in the scoping conversation; reopening the question would be process-violation.

The decision is recorded in ADR-0011: **the YAML on disk is the source of truth; there is no in-app catalog mutation path in v1, and no MCP catalog-mutation tool.**

### R-8. Scope-selector grammar (shared with PrerequisiteRule)

The selector vocabulary is intentionally narrow:

```yaml
# All AND'd together; no disjunction in v1.
vendor_normalized: cisco         # exact string
platform_family: iosxr           # exact string
region_in: [oslo, bergen]        # set membership
site_in: [oslo-1]                # set membership
role_in: [edge-router]           # set membership
hardware_revision_in: [v2, v3]   # set membership
not_in_state: [outside_target]   # set membership against LifecycleState
tagged_with: [edge]              # DEFERRED — schema-valid, evaluator returns unknown
```

Disjunction is not in v1. If a target needs "oslo OR bergen", the operator writes one selector with `region_in: [oslo, bergen]`. If a target needs "oslo edge-routers OR bergen core-routers", they write two separate target YAMLs. Two targets, two policies, no boolean algebra; this is fine for v1 and removes a class of bugs.

### R-9. Out-of-scope hard boundary list (for future-feature reviewers)

Documented here so reviewers of F3+ know what F2 explicitly punts:

| Defer to | Item |
|---|---|
| F3 | Drift taxonomy on the compliance envelope (`reasons[].kind` will grow new variants); `recommended_actions` |
| F4 | `evaluate_prerequisites(device_id)`; `explain_blockers` MCP tool; readiness verdict |
| F5 | MCP catalog-mutation tools; uplift plans; wave approval |
| F6 | End-to-end Cisco ISR1121 vertical slice |
| F7 | NetBox-sourced device tags → makes `tagged_with` evaluable |
| post-v1 | CVE / NVD matching; S3 BlobStore; auto-poll of vendor firmware feeds; in-app catalog edit |

If reviewing F2's tasks.md and you see something from this list landing inside F2, that's a scope creep; flag it.

---

## Open questions

None. All NEEDS CLARIFICATION markers from spec.md have been resolved either at scoping time (chat history, locked F2 brief) or in the decisions above.
