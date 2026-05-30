# ADR-0011 — Firmware catalog: YAML as source of truth, git as approval, no in-app mutation

- **Status**: Accepted
- **Date**: 2026-05-29
- **Feature**: F2 (`002-firmware-catalog`)
- **Source decisions**: research.md D1, D2, D3, D5, R-7
- **Constitution principles**: I (Governance Before Execution), IV (Lifecycle-as-Code), V (Evidence, Audit & Explainability)

## Context

F2 introduces firmware policy into GARD: `FirmwareTarget` says "devices matching this selector should be on this version"; `FirmwarePackage` declares an installer artefact; `UpgradePath` declares edges in the version graph; `PrerequisiteRule` declares conditions that must hold before an upgrade.

We need to answer four questions before writing the loader:

1. **Where does the catalog live?** Disk YAML, DB rows, an in-app editor, or some mix.
2. **How is it approved?** PR review, in-app workflow, or out-of-band.
3. **How is its history audited?** By file commit, by row insert, or both.
4. **What's the seam to future implementations** (e.g. an S3-backed blob store, a vendor-feed ingest path)?

The temptation in F1 was to mirror its three-tier resolution (Manual → DB → File) for firmware too. F1's design was the right answer for *normalization rules*, where overnight migrations need a hot-fix path. Firmware *policy* is a different beast — it should change with the same gravity as any other infrastructure-as-code commit.

## Decision

### 1. Storage authority

**YAML on disk is the single source of truth.** The four catalog entity kinds (`FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule`) live under `gard-catalog/firmware/{targets,packages,upgrade-paths,prerequisites}/*.yaml`. The corresponding Postgres tables (`firmware_targets`, `firmware_packages`, `firmware_upgrade_paths`, `firmware_prerequisite_rules`) are a **read-through cache** rebuilt by the loader. There is no DB-override layer and no manual-mapping layer. **Approval = merged PR.**

This is a deliberate retraction of ADR-0010's three-tier model for the firmware domain. Hot-fixes are still possible — they just look like "open a PR, get review, merge". The trade-off is reduced operational ergonomics in exchange for a single, auditable, reversible authority surface. Catalogs that exist to *codify decisions* (firmware policy) get one source; catalogs that exist to *normalise observations* (rules) get layered storage.

### 2. Schema and versioning

All four entity kinds and the shared `ScopeSelector` are described by JSON Schema 2020-12 files in `specs/002-firmware-catalog/contracts/`, with runtime copies in `gard/catalog/schemas/firmware/`. Every YAML file carries a top-level `catalog_schema_version: "1.0.0"` field; the loader rejects mismatched versions outright. Schema bumps are minor (additive) or major (breaking); 1.0.x stays back-compat with the v1 vocabulary.

### 3. Git SHA anchoring

Every loaded row records `loaded_from_git_sha` set to the **file's** most-recent commit SHA, obtained via `git log -1 --format=%H -- <relpath>`. **Not** the worktree HEAD. This means a bulk reload of unchanged files re-emits zero audit rows (idempotent) and a single-file edit gets a single-file audit row. In `GARD_ENV=prod` the loader refuses to operate against a dirty worktree (any tracked-file change) and exits non-zero. In dev, dirty loads are permitted but write `loaded_from_git_sha = NULL` + emit a `dirty=true` audit annotation so accidental hot-loads surface in the chain.

### 4. Soft-delete

Catalog rows carry a nullable `removed_at TIMESTAMPTZ`. The API filters `removed_at IS NULL`; removed rows persist in the table indefinitely (no GC in v1). Re-introducing a YAML file with identical natural key (`name` for targets/prereqs, `(vendor, platform_family, version)` for packages, `(platform_family, from_version, to_version)` for upgrade-path edges) resurrects the row by clearing `removed_at` and updating `loaded_from_git_sha` + `loaded_at`. Audit chain walkability across removals is the primary motivator: a `firmware_target.compliance_evaluated` audit row from six months ago must still dereference its `target_ref`.

### 5. Transactional load

The loader is **all-or-nothing**. A single transaction wraps validate → upsert → soft-delete-missing across all four entity kinds. Any schema violation, FS conflict, duplicate-identity collision, or unknown scope-selector key rolls the entire reload back; one `firmware_catalog.reload_failed` audit row records the offending file + reason. The pre-reload catalog state is preserved exactly — adversarial-input tests assert this against ≥20 malformed cases per spec SC-004.

### 6. BlobStore protocol seam

Firmware *artefacts* (the installer binary) optionally live in a separate `BlobStore`, accessed through a five-method `typing.Protocol` (`put`, `get`, `exists`, `delete`, `iter_keys`). v1 ships one concrete implementation: `LocalFsBlobStore` rooted at `GARD_BLOB_ROOT` (default `/var/lib/gard/blobs/`). Blobs are content-addressed by SHA-256 (`sha256/<first2>/<remaining62>.bin`); SHA verification happens chunked during write AND chunked during every read. The protocol shape is what enables a future S3-backed implementation as an additive change rather than a refactor through the whole catalog. **The protocol is not exposed via any public API** — callers go through the FastAPI router or the loader, never through the protocol directly.

This is a bounded retraction of F1 research D2's "no object store in v1" stance: the retraction applies *only* to firmware-package blobs. Evidence, audit, normalization artefacts, MCP session storage, and every other concern remain DB-resident.

### 7. No in-app catalog mutation

There is no `POST /api/v1/firmware/targets`. There is no `MANAGE_FIRMWARE_CATALOG` permission. There is no MCP catalog-mutation tool. The only way to change a firmware target, package, upgrade-path edge, or prerequisite rule is to merge a PR to `gard-catalog`. This is the constitutional reading of Principle IV at full strength and the binding outcome of research.md R-7's design pressure test.

### 8. Boot-time reload failure posture

A reload failure at app startup MUST NOT crash the API. The lifespan handler logs the failure (structured: `event=firmware_catalog.boot_reload_failed`, with the failing file path + reason), emits one `firmware_catalog.reload_failed` audit row, and continues — serving the last-known catalog state from the previous successful reload. The next lifespan signal (worker restart, SIGHUP-style reload, or an explicit `gard catalog reload firmware`) retries. This is the safe failure mode: "serve stale, fail loud" beats "fail to start" for an observability/policy plane where the catalog evolves continuously but the API must remain available.

## Consequences

- Operators learn one mental model for firmware catalog changes: edit YAML, open PR, merge. Identical to how normalization rules ship in F1 *minus* the DB-override escape hatch. The trade-off is consciously asymmetric.
- The audit chain stays walkable across removals — old `target_ref` dereferences keep working because `removed_at IS NOT NULL` rows are still present.
- The append-only DB role established in F1 is **not** the writer of catalog tables (soft-delete is an UPDATE, which the append-only role can't do). The regular `gard_writer` role owns catalog mutation; the append-only role continues to own `audit_events` + `lifecycle_evidence` writes only.
- Adding a new entity kind in F3+ is mechanical: a JSON Schema file, an Alembic migration, ORM model, loader function, controller, router. The seam is well-defined.
- A future S3-backed `BlobStore` is a 1-file diff against the protocol — no consumer refactor required.
- We accept the small ergonomic cost of "must commit to test": dev workflows can use `GARD_ENV=dev` to load dirty trees, but those rows carry `loaded_from_git_sha=NULL` and a dirty annotation that's visible in every API response.

## Alternatives considered

- **DB-override layer for firmware too (mirror ADR-0010).** Rejected: reintroduces in-app authoring through the back door; conflicts with the explicit "approval = merged PR" decision; doubles the audit story for marginal hot-fix ergonomics that the firmware domain doesn't actually need.
- **In-app `Approver` role pushing back to YAML via a git-add API.** Rejected (the design pressure test in research R-7): adds an authorization seam the constitution doesn't have a vocabulary for; muddies the audit story; the user explicitly chose git-native.
- **Anchor `loaded_from_git_sha` to worktree HEAD.** Rejected: a single bulk reload would tag unrelated files with the same SHA, defeating per-file precision.
- **Hard-delete on YAML removal.** Rejected: cascades the unknown into the lifecycle state machine ugly, breaks dereferencing of historical audit rows.
- **Postgres LO / bytea for firmware blobs.** Rejected: LO replication is awkward, ties blob lifecycle to row lifecycle (so soft-deleted packages drop their blobs prematurely), inflates DB backups by GB.
- **Mount cloud storage directly in v1.** Rejected: introduces credential surface + network path, both explicitly out of v1 scope per the spec.

## References

- spec.md (FR-001..FR-007, FR-038, FR-042, FR-043; SC-002, SC-003, SC-004, SC-005)
- research.md §D1 (schema versioning), §D2 (git SHA capture), §D3 (soft-delete), §D5 (BlobStore protocol), §R-7 (approval-model pressure test)
- data-model.md §1 (catalog tables), §2 (BlobStore protocol), §7 (migration order)
- contracts/firmware-target.schema.yaml, firmware-package.schema.yaml, firmware-upgrade-path.schema.yaml, firmware-prerequisite.schema.yaml, scope-selector.schema.yaml
- ADR-0009 (audit & evidence storage) — append-only role unchanged in F2
- ADR-0010 (normalization rules format) — F2 deliberately *does not* mirror its three-tier model
