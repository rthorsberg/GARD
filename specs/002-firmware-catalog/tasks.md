# Tasks: Firmware Catalog

**Input**: Design documents from `/specs/002-firmware-catalog/`
**Prerequisites**: plan.md, spec.md, research.md (D1–D8 + R-1…R-9), data-model.md, contracts/, quickstart.md
**Tests**: REQUIRED. The constitution mandates contract + integration tests for every controller boundary, REST endpoint, MCP tool, catalog YAML schema, and predicate grammar.

## Format

`- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Different files, no dependency on incomplete tasks — runnable in parallel.
- **[USn]**: Required on user-story-phase tasks; omitted on Setup, Foundational, and Polish.

---

## Phase 1: Setup

**Purpose**: Pin the catalog ADR, declare the new dependency + env knob, and stage the dev fixtures so every later phase has a deterministic ground truth to load.

- [ ] T001 [P] Write `adr/ADR-0011-catalog-yaml-schema-and-precedence.md` consolidating research.md D1+D2+D3+D5+R-7: JSON Schema 2020-12, semver header `catalog_schema_version: 1.0.0`, file-SHA git anchoring (not HEAD), soft-delete via `removed_at`, `BlobStore` protocol seam, and the binding "approval = merged PR, no in-app catalog mutation" rule. Include a §"Boot-time reload failure posture" addendum: structured-log + serve last-known catalog state rather than crashing the API; subsequent reload retried on the next lifespan signal
- [ ] T002 [P] Add `networkx>=3.2` to `pyproject.toml` dependencies (single new third-party dep for F2)
- [ ] T003 [P] Extend `deploy/docker-compose.yml`: add named volume `deploy_gard-blobs` mounted at `/var/lib/gard/blobs/` on the `api` service; add `GARD_BLOB_ROOT=/var/lib/gard/blobs` to the `api` env block; update `deploy/.env.example` with `GARD_BLOB_ROOT` + `GARD_FIRMWARE_BLOB_MAX_BYTES`
- [ ] T004 [P] Seed gard-catalog fixtures: create `gard-catalog/firmware/{targets,packages,upgrade-paths,prerequisites}/` and write the four representative YAMLs from plan.md project structure (`cisco-iosxr-edge.yaml`, `juniper-junos-core.yaml`, `cisco-iosxr-7.5.2.yaml`, `juniper-junos-22.4R3-S2.yaml`, `cisco-iosxr.yaml`, `juniper-junos.yaml`, `iosxr-minimum-disk.yaml`) — each with `catalog_schema_version: "1.0.0"`
- [ ] T005 [P] Mirror fixtures into `deploy/scripts/fixtures/firmware/` so `make seed` can load them deterministically in CI and on `make reset`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration (enum extension + device cols + 4 catalog tables), ORM models, the shared selector + graph + blob primitives, the JSON-Schema-validating loader, and the RBAC additions. **No user-story work may begin until this phase is complete.**

### Migration

- [ ] T006 Alembic migration `gard/db/migrations/versions/0002_firmware_catalog.py` per data-model.md §7. Apply in this exact order: (1–3) `ALTER TYPE lifecycle_state_kind ADD VALUE` for `target_defined`, `compliant`, `outside_target` (autocommit block, idempotent guard); (4) `ALTER TABLE devices ADD COLUMN ram_mb INTEGER`, `disk_mb INTEGER`, `licenses TEXT[]`; (5) `CREATE TABLE firmware_targets` + indexes (incl. partial UNIQUE on `name WHERE removed_at IS NULL`); (6) `CREATE TABLE firmware_packages` + indexes (incl. partial UNIQUE on `(vendor, platform_family, version) WHERE removed_at IS NULL`); (7) `CREATE TABLE firmware_upgrade_paths` + indexes; (8) `CREATE TABLE firmware_prerequisite_rules` + indexes. Grants: the regular `gard_writer` role is the writer of catalog tables (loader does soft-delete UPDATE); `gard_writer_append_only` is not granted on catalog tables. Downgrade raises `NotImplementedError("0002 downgrade not supported; see runbook")`.

### Models

- [ ] T007 [P] Extend `gard/models/_enums.py`: add `LifecycleState.TARGET_DEFINED`, `LifecycleState.COMPLIANT`, `LifecycleState.OUTSIDE_TARGET`; keep ordering stable with existing F1 enum values
- [ ] T008 [P] `gard/models/firmware_target.py`: SQLAlchemy 2.x ORM model with the column shape from data-model.md §1.1 (id, name, platform_family, target_version, scope_selector JSONB, valid_from, valid_until, notes, loaded_from_git_sha, loaded_at, removed_at, source_file_relpath, catalog_schema_version)
- [ ] T009 [P] `gard/models/firmware_package.py`: matches data-model.md §1.2 (vendor, platform_family, version, sha256, byte_size, signed_by, release_date, download_url, notes, blob_present, blob_stored_at + common columns)
- [ ] T010 [P] `gard/models/firmware_upgrade_path.py`: matches data-model.md §1.3 (platform_family, from_version, to_version, weight, notes + common columns)
- [ ] T011 [P] `gard/models/firmware_prerequisite.py`: matches data-model.md §1.4 (name, applies_to JSONB, predicate_kind, predicate_args JSONB, severity, evaluable + common columns)
- [ ] T012 [P] Extend `gard/models/device.py`: add `ram_mb: Mapped[int | None]`, `disk_mb: Mapped[int | None]`, `licenses: Mapped[list[str] | None]` (Postgres `ARRAY(TEXT)`); keep all existing F1 columns and indexes
- [ ] T013 [P] Register new models in `gard/models/__init__.py` (no schema change beyond imports)

### Core utilities

- [ ] T014 [P] `gard/core/scope_selector.py`: pure functions `matches(selector: dict, facts: dict) -> bool` and `specificity(selector: dict) -> int` (count of non-null leaf entries; each set-membership counts once). Selector grammar from research.md R-8 (AND-only, no disjunction); raises `UnknownSelectorKey` on unknown keys (loader catches → reload_failed)
- [ ] T015 [P] `gard/core/blob_store/__init__.py`: declare the `BlobStore` typing.Protocol with the five methods from data-model.md §2; declare `WriteReceipt` (computed_sha256, bytes_written, stored_at) and `StreamWithVerify` (wraps `io.BufferedReader` + side-channel `hashlib.sha256()` with `.verify_at_eof()`); declare `BlobChecksumMismatch`, `BlobUploadInProgress`, `BlobTooLarge`, `BlobNotPresent` exceptions
- [ ] T016 `gard/core/blob_store/local_fs.py`: `LocalFsBlobStore` concrete impl. Content-addressed paths `sha256/<first2>/<remaining62>.bin` under `GARD_BLOB_ROOT`. `put()` streams 8 MiB chunks to `<final>.tmp.<uuid7>` with `hashlib.sha256` incremental update, atomic `os.rename` on SHA match, deletes temp file on mismatch. `get()` returns `StreamWithVerify` that recomputes SHA chunked and exposes `.verify_at_eof()`. Concurrency: `fcntl.flock(LOCK_EX | LOCK_NB)` on a sibling `<final>.lock` file; `BlockingIOError` → `BlobUploadInProgress`. Includes `iter_keys()` for audit tooling. Depends on T015
- [ ] T017 [P] `gard/core/upgrade_path_graph.py`: `UpgradePathGraphCache` keyed by `platform_family`, built lazily from `firmware_upgrade_paths` rows where `removed_at IS NULL`. Uses `networkx.DiGraph`. `shortest_path(platform_family, from_v, to_v)` returns `(chain: list[str], total_weight: int | None, hops: int, reason_kind: str | None)`. Handles cycles (visited set is implicit in networkx Dijkstra), `from == to` → `(chain=[from], total_weight=0, hops=0, None)`, no platform → `("platform_not_found", ...)`, no path → `([], None, 0, "no_path")`. Cache invalidation API for the loader to call after each reload pass
- [ ] T018 [P] Copy contract JSON Schemas into runtime path `gard/catalog/schemas/firmware/`: `firmware-target.schema.yaml`, `firmware-package.schema.yaml`, `firmware-upgrade-path.schema.yaml`, `firmware-prerequisite.schema.yaml`, `scope-selector.schema.yaml` (verbatim from `specs/002-firmware-catalog/contracts/`). Tests in T022 + T026 + T036 + T045 + T046 + T055 lock these in place

### Catalog loader + controller

- [ ] T019 `gard/core/firmware_catalog_loader.py`: single transactional `load(session, root_path: Path) -> LoadReceipt`. Reads `targets/`, `packages/`, `upgrade-paths/`, `prerequisites/` YAML trees → validates each file against the matching JSON Schema (`jsonschema` Draft 2020-12 validator) → upserts (resurrecting `removed_at`-set rows by setting `removed_at = NULL` + bumping `loaded_at`/`loaded_from_git_sha`) → soft-deletes (`removed_at = now()`) rows whose `source_file_relpath` is no longer on disk. Any validation, FS conflict, or duplicate-identity error rolls the whole transaction back. Returns `LoadReceipt(loaded, removed, unchanged, dirty_loads)`. Depends on T008–T013, T018
- [ ] T020 `gard/core/firmware_catalog_controller.py`: orchestration layer. `reload(root_path)` calls the loader, captures the file's git SHA via `git log -1 --format=%H -- <relpath>` per file (subprocess; per research D2). If working tree is dirty AND `GARD_ENV == "prod"`: refuse + emit `firmware_catalog.reload_failed`. Emits one `firmware_catalog.<entity>.{loaded,removed}` `AuditEvent` per row change with `loaded_from_git_sha` populated; emits one `firmware_catalog.reload_failed` on rollback. Hooks the loader into the existing FastAPI lifespan handler (app boot reload), idempotent (zero audit emits on no-change re-runs). Depends on T019
- [ ] T021 [P] Extend `gard/__main__.py`: add `gard catalog reload firmware` subcommand calling the controller; also extend the existing `gard catalog reload` to reload normalization + firmware in a single transaction. Both invocations MUST remain idempotent — re-running against an unchanged tree emits zero audit rows (per spec.md Assumption "App-boot reload is idempotent")

### Settings, RBAC, CSV, ADR-0011-touching wiring

- [ ] T022 [P] `gard/core/settings.py`: add `blob_root: Path = Path("/var/lib/gard/blobs")` (env `GARD_BLOB_ROOT`), `firmware_blob_max_bytes: int = 5 * 1024 ** 3` (env `GARD_FIRMWARE_BLOB_MAX_BYTES`)
- [ ] T023 [P] `gard/core/rbac.py`: add `READ_FIRMWARE_CATALOG` (granted to `viewer`, `lifecycle_manager`, `mcp_client`, `system_admin`) and `MANAGE_FIRMWARE_BLOB` (granted to `lifecycle_manager`, `system_admin`). **No** `MANAGE_FIRMWARE_CATALOG` permission (per FR-038)
- [ ] T024 [P] CSV importer (`gard/core/csv_import.py` or equivalent): bump `csv_schema_version` to `1.1.0`; accept optional `ram_mb`, `disk_mb`, `licenses` columns; `licenses` is semicolon-separated → `list[str]` with per-element whitespace trimmed and empty entries skipped (comma-separated lists are rejected, surfacing as a row-level error rather than a silent split); v1.0.0 CSVs continue to load (additive). Amend `specs/001-device-import-normalize/contracts/csv-schema.yaml` additively
- [ ] T025 [P] Extend `gard/core/envelope.py`: add `FirmwareComplianceEnvelope` variant carrying `target_ref`, `target_version`, `observed_version` alongside the standard `state/summary/reasons/confidence/as_of/correlation_id` fields from F1 ADR-0005

**Checkpoint**: Foundation ready — DB shape, models, loader, BlobStore, RBAC, settings, CSV bump, and envelope variant are all in place. User stories can begin in any order, but US1+US2 are the MVP.

---

## Phase 3: User Story 1 - Operator sees firmware compliance per device (Priority: P1) 🎯 MVP

**Goal**: `GET /api/v1/devices/{id}/firmware-compliance` returns a deterministic envelope with `state ∈ {compliant, outside_target, target_defined, classified, unknown}`, citing the resolved target and version comparison.

**Independent Test**: Load a `FirmwareTarget` covering `iosxr` + `junos`, re-import F1's device fixture, hit `GET /api/v1/devices/{r1.id}/firmware-compliance` for a match and a mismatch — both responses cite the matched target id, the version comparison, and a `correlation_id`. A device with `observed_firmware = NULL` returns `state=unknown`.

### Tests for User Story 1

- [ ] T026 [P] [US1] `tests/contract/test_firmware_compliance_envelope.py`: locks the response shape against `contracts/rest-openapi.yaml` (state enum, reasons discriminator, nullable `target_ref`/`observed_version`, correlation_id present)
- [ ] T027 [P] [US1] `tests/integration/test_us1_firmware_compliance_per_device.py`: end-to-end against live Postgres — load fixture targets, run CSV import, walk every AC-1.x from spec.md (compliant / outside_target / unknown / no_target_matched / empty_catalog)
- [ ] T028 [P] [US1] `tests/unit/test_scope_selector_specificity.py`: covers AND-only semantics, specificity counting, tie-break by `loaded_at DESC` (deterministic), unknown-key rejection

### Implementation for User Story 1

- [ ] T029 [US1] `gard/core/compliance_controller.py`: `evaluate(session, device_id) -> ComplianceEnvelope`. Loads device facts → calls `scope_selector.matches()` against every active `firmware_targets` row → picks the most-specific match (ties: `loaded_at DESC`) → compares `device.observed_firmware` to `target.target_version` → returns envelope. On state change: writes the new `lifecycle_state` to the device AND emits `firmware_target.compliance_evaluated` `AuditEvent` with `before/after` state, `target_ref`, `correlation_id`. Idempotent — no audit emit when state is unchanged. Depends on T014, T020
- [ ] T030 [US1] `gard/api/schemas/firmware_compliance.py`: Pydantic v2 response model matching `FirmwareComplianceEnvelope` from T025, with `reasons` as a discriminated union (`target_matched`, `version_match`, `version_mismatch`, `target_runner_up`, `missing_observation`, `no_target_matched`, `empty_catalog`)
- [ ] T031 [US1] `gard/api/routers/firmware_compliance.py`: `GET /api/v1/devices/{id}/firmware-compliance` calling `compliance_controller.evaluate()`; depends on `require(READ_FIRMWARE_CATALOG)`; returns 404 only when the device itself is missing; register on `gard/api/app.py` under tag `firmware-compliance`
- [ ] T032 [US1] Hook `compliance_controller.evaluate()` into the CSV import device-update path so every accepted observation produces a fresh state on the next read. Touch point: the existing F1 import controller where `Device.observed_firmware` is set

**Checkpoint**: US1 MVP done. Operator can answer "is device X on its target?" end-to-end. This is one half of the F2 MVP (paired with US2). Commit + push, run CI.

---

## Phase 4: User Story 2 - Operator publishes a new firmware target via PR (Priority: P1) 🎯 MVP

**Goal**: Operators can commit YAML to `gard-catalog/firmware/targets/`, run `gard catalog reload firmware` (or restart the app), and see the target appear in `GET /api/v1/firmware/targets` with its git SHA in the audit trail. Reverting the commit removes it.

**Independent Test**: Commit `cisco-iosxr-edge.yaml` → reload → `GET /api/v1/firmware/targets` lists it with `loaded_from_git_sha`. Audit row carries the git SHA. Delete the file → reload → row disappears (soft-deleted), retraction audit row emitted, any device whose lifecycle was driven by it re-enters `classified`.

### Tests for User Story 2

- [ ] T033 [P] [US2] `tests/contract/test_firmware_target_yaml_schema.py`: load each schema, accept the fixture YAMLs, reject 6 malformed variants (missing field, unknown predicate, schema violation, unknown selector key, schema_version mismatch, additionalProperties)
- [ ] T034 [P] [US2] `tests/integration/test_us2_git_native_target_authoring.py`: walks AC-2.1, AC-2.2, AC-2.4 from spec.md (well-formed → loaded, malformed → rolled back, listing returns git SHA)
- [ ] T035 [P] [US2] `tests/integration/test_loader_transactional_rollback.py`: adversarial pack — at least 20 malformed YAML cases (per SC-004), every one rolls the whole reload back and the pre-reload catalog state is preserved exactly
- [ ] T036 [P] [US2] `tests/integration/test_catalog_reload_audit_chain.py`: verifies one `firmware_catalog.target.loaded` audit row per loaded file with `after.git_commit_sha` populated; reverting the file emits `firmware_catalog.target.removed`; the daily chain seal from F1 still validates the new audit rows

### Implementation for User Story 2

- [ ] T037 [P] [US2] `gard/api/schemas/firmware_target.py`: Pydantic response model with the eight fields exposed by `GET /firmware/targets` (id, name, platform_family, target_version, scope_selector, valid_from, valid_until, notes, loaded_from_git_sha, loaded_at, source_file_relpath)
- [ ] T038 [US2] `gard/api/routers/firmware_targets.py`: `GET /api/v1/firmware/targets` (paginated list), `GET /api/v1/firmware/targets/{id}` (single by UUID). Filters: `platform_family`, `name`. Auth: `require(READ_FIRMWARE_CATALOG)`. Filters `removed_at IS NULL`. Register on `app.py`
- [ ] T039 [US2] Extend FastAPI lifespan handler in `gard/api/app.py`: after the existing F1 normalization-catalog reload on boot, call `firmware_catalog_controller.reload()` (idempotent). Failures log a structured error but **do not** crash the app — the API serves stale catalog rather than dying (per the constitutional "fail safe, fail loud" reading)
- [ ] T040 [US2] Extend `firmware_catalog_controller.reload()` from T020 with a post-pass hook: after a successful reload, queue a `compliance_controller.evaluate()` for every device whose `lifecycle_state` is currently `target_defined`/`compliant`/`outside_target` OR whose scope_selector matches a newly loaded/removed target row. Bounded re-evaluation, not "the whole device table". Depends on T020, T029
- [ ] T041 [US2] Extend `deploy/scripts/seed.sh`: after the device CSV import, mint a token + POST a `gard catalog reload firmware` (or call the controller via a one-shot CLI subcommand inside the container). Extend the `Makefile` `seed` target so `make seed` and `make reset` produce a fully populated F1+F2 dev environment
- [ ] T042 [US2] Add a representative `cisco-iosxr-edge.yaml` and matching prereq + upgrade-path YAML into `deploy/scripts/fixtures/firmware/` that turns at least 2 of the 5 seed devices into `compliant` and at least 1 into `outside_target` once seeded — gives `make seed` a non-trivial demo state

**Checkpoint**: F2 MVP complete (US1 + US2). PR #2 can flip from draft to ready here — compliance reads + git-native policy authoring both work. Commit + push, run CI, mark PR ready.

---

## Phase 5: User Story 3 - Operator queries upgrade paths and prerequisites (Priority: P2)

**Goal**: `GET /api/v1/firmware/upgrade-paths` returns shortest-weight chains; `GET /api/v1/firmware/prerequisites` lists rules with their `evaluable` flag.

**Independent Test**: Load `cisco-iosxr.yaml` with edges `7.4.1→7.5.2 (w=1)`, `7.5.2→7.8.1 (w=1)`, `7.4.1→7.8.1 (w=5)`. Query `?from=7.4.1&to=7.8.1` returns `chain=[7.4.1, 7.5.2, 7.8.1]`, `total_weight=2`. `?from=7.4.1&to=99.0.0` returns `chain=[]`, `reasons[0].kind=no_path` (HTTP 200, not 404). Load a `tagged_with` prerequisite → appears with `evaluable=false`.

### Tests for User Story 3

- [ ] T043 [P] [US3] `tests/contract/test_firmware_upgrade_path_yaml_schema.py`: schema accepts valid edge sets, rejects empty `edges` array, negative weights, missing fields
- [ ] T044 [P] [US3] `tests/contract/test_firmware_prerequisite_yaml_schema.py`: every one of the 9 predicate kinds validates; unknown `kind` rejected; `tagged_with` accepted but marked `evaluable=false` at load time
- [ ] T045 [P] [US3] `tests/integration/test_us3_upgrade_path_and_prerequisites.py`: walks AC-3.1…AC-3.4 from spec.md
- [ ] T046 [P] [US3] `tests/unit/test_upgrade_path_dijkstra.py`: shortest-path correctness, `from==to` zero-hop, cycle defensiveness (A→B→A→B…), no-path discrimination from missing-platform, 500-edge perf smoke
- [ ] T047 [P] [US3] `tests/unit/test_prerequisite_grammar.py`: each predicate's `predicate_args` shape validates, `tagged_with` short-circuits to `evaluable=false`, `not_in_state` rejects unknown state names

### Implementation for User Story 3

- [ ] T048 [P] [US3] `gard/api/schemas/firmware_upgrade_path.py`: response models for `UpgradePathChain` (chain, total_weight, hop_count, reasons[]) and `UpgradePathEdge` (platform_family, from_version, to_version, weight, notes, loaded_from_git_sha)
- [ ] T049 [P] [US3] `gard/api/schemas/firmware_prerequisite.py`: response model with `name`, `applies_to`, `predicate_kind`, `predicate_args`, `severity`, `evaluable`, `loaded_from_git_sha`
- [ ] T050 [US3] `gard/api/routers/firmware_upgrade_paths.py`: `GET /api/v1/firmware/upgrade-paths` with query params `platform_family`, `from_version`, `to_version` → calls `upgrade_path_graph.shortest_path()` → returns `UpgradePathChain`. Also `GET /api/v1/firmware/upgrade-paths/edges?platform_family=X` listing raw edges. Auth: `require(READ_FIRMWARE_CATALOG)`. Register on `app.py`. Depends on T017, T020
- [ ] T051 [US3] `gard/api/routers/firmware_prerequisites.py`: `GET /api/v1/firmware/prerequisites` listing rules with filter `predicate_kind`. Auth: `require(READ_FIRMWARE_CATALOG)`. Register on `app.py`
- [ ] T052 [US3] Loader extension (in `firmware_catalog_loader.py`, T019): when a prerequisite rule's `predicate_kind == 'tagged_with'`, set `evaluable = False` at upsert; for all other kinds set `evaluable = True`. Emit no `predicate_deferred` audit reason at load (that's an F4 concern); the row simply carries the flag

**Checkpoint**: US3 done — upgrade graph + prereq grammar live. Commit + push.

---

## Phase 6: User Story 4 - Operator uploads and downloads a verified firmware package (Priority: P2)

**Goal**: Operators can attach a real installer binary to a `FirmwarePackage` row; the SHA-256 is verified on write and again on every read; tampering is detected.

**Independent Test**: Upload a 100 MB binary whose SHA matches the YAML's `sha256`. `POST .../blob` returns 200 with `computed_sha256`. `GET .../blob` streams the bytes with matching SHA and `X-GARD-SHA256` header. Tamper (test-only) → next GET returns HTTP 500 `code=blob_checksum_mismatch_on_read` + audit row.

### Tests for User Story 4

- [ ] T053 [P] [US4] `tests/contract/test_firmware_package_yaml_schema.py`: vendor enum, sha256 hex pattern, byte_size bounds (1…5_368_709_120), `download_url` URI format
- [ ] T054 [P] [US4] `tests/integration/test_us4_blob_upload_download.py`: walks AC-4.1…AC-4.5 (happy, mismatch, oversize, mismatch-on-read, missing-blob). Uses `tmp_path` for an isolated blob root
- [ ] T055 [P] [US4] `tests/unit/test_blob_store_local_fs.py`: chunked SHA correctness on streams of varying sizes (0 bytes, exactly chunk-size, chunk-size+1, multi-GB synthesised), atomic-rename guarantee (interrupted write leaves no final file), `flock` serialisation under concurrent puts

### Implementation for User Story 4

- [ ] T056 [P] [US4] `gard/api/schemas/firmware_package.py`: response model for listing + single-get; separate `BlobUploadReceipt` (computed_sha256, bytes_written, stored_at)
- [ ] T057 [US4] `gard/api/routers/firmware_packages.py`: (1) `GET /api/v1/firmware/packages` with optional `vendor`/`platform_family` filters, `require(READ_FIRMWARE_CATALOG)`; (2) `GET /api/v1/firmware/packages/{id}` same auth; (3) `POST /api/v1/firmware/packages/{id}/blob` requiring `MANAGE_FIRMWARE_BLOB`, streams chunked into `LocalFsBlobStore.put()`, returns 200/422/413/409 per FR-029/031/033, emits `firmware_catalog.package.blob_stored` `AuditEvent` + `firmware_package_upload` `LifecycleEvidence` on success, sets `firmware_packages.blob_present = TRUE` and `blob_stored_at = now()`; (4) `GET /api/v1/firmware/packages/{id}/blob` requiring `READ_FIRMWARE_CATALOG`, streams from `LocalFsBlobStore.get()` with `verify_at_eof()`, sets `X-GARD-SHA256` and `Content-Length` headers, on mismatch returns 500 + emits `firmware_catalog.package.blob_read_failed`. Register on `app.py`. Depends on T015, T016, T020
- [ ] T058 [US4] Extend `gard/api/routers/health.py` (`/healthz`): when the running role can reach `MANAGE_FIRMWARE_BLOB`, verify `GARD_BLOB_ROOT` is writable; failures degrade `status` to `degraded` (not `unhealthy` per FR-045)
- [ ] T059 [US4] Extend `gard/core/firmware_catalog_controller.py`: per loader pass, emit one `firmware_catalog_load` `LifecycleEvidence` row with `source_checksum = SHA-256(<sorted list of loaded git SHAs>)` for Merkle-style chain-of-custody (per data-model.md §5). Depends on T020

**Checkpoint**: US4 done — package blobs end-to-end with checksum guarantees on both writes and reads. Commit + push.

---

## Phase 7: User Story 5 - MCP-mediated agent answers firmware questions (Priority: P3)

**Goal**: Exactly five new read-only MCP tools available; identical answers (byte-for-byte after envelope normalisation) to the REST endpoints; disallowed tools rejected.

**Independent Test**: An MCP client calls `get_target_firmware(device_id=<r2.id>)` and receives the same payload as `GET /api/v1/devices/{r2.id}/firmware-compliance`. `get_upgrade_path` returns the same chain as the REST query. `execute_sql` (not on the list) returns `code=tool_not_found`.

### Tests for User Story 5

- [ ] T060 [P] [US5] `tests/contract/test_firmware_mcp_tools.py`: locks the five tools' input/output schemas against `contracts/mcp-tools.yaml`
- [ ] T061 [P] [US5] `tests/integration/test_us5_mcp_firmware_tools.py`: walks AC-5.1…AC-5.4 (list returns exactly the 5+F1 tools; `get_target_firmware` matches REST byte-for-byte after correlation_id is stripped; disallowed tool rejected; auth-denied path emits `auth.denied`)

### Implementation for User Story 5

- [ ] T062 [P] [US5] `gard/mcp/tools/get_target_firmware.py`: input `{device_id: str}`, output mirrors `FirmwareComplianceEnvelope`. Delegates to `compliance_controller.evaluate()`. Auth via the F1 MCP auth dependency; emits the same audit row family as the REST equivalent
- [ ] T063 [P] [US5] `gard/mcp/tools/get_upgrade_path.py`: input `{platform_family, from_version, to_version}`, output `UpgradePathChain`. Delegates to `upgrade_path_graph.shortest_path()`
- [ ] T064 [P] [US5] `gard/mcp/tools/list_firmware_targets.py`: input `{filter?: {platform_family?, name?}}`, output list of `FirmwareTarget` (cap at `MCP_LIST_MAX_RETURN`)
- [ ] T065 [P] [US5] `gard/mcp/tools/list_firmware_packages.py`: input `{filter?: {vendor?, platform_family?}}`, output list of `FirmwarePackage` (cap)
- [ ] T066 [P] [US5] `gard/mcp/tools/list_upgrade_paths.py`: input `{platform_family?}`, output list of `UpgradePathEdge` (cap)
- [ ] T067 [US5] Register all five tools on the existing MCP server (`gard/mcp/server.py` or wherever F1 registered tools). Verify the F1 disallowed-tool envelope still rejects anything outside the published F1+F2 list. Depends on T062–T066

**Checkpoint**: All five user stories done. Commit + push. The full F2 PR is now reviewable end-to-end.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T068 [P] `tests/contract/test_firmware_rest_openapi.py`: lock the F2 REST shape against `contracts/rest-openapi.yaml` — every new path, schema, and response code is present and the generated `openapi.json` matches the contract. Catches future drift
- [ ] T069 [P] `tests/integration/test_compliance_state_machine.py`: walks every cell of the transition matrix in data-model.md §3.3 (classified→target_defined→compliant; target_defined→outside_target; observation-change recompute; reload-removes-target retract; soft-delete-then-resurrect). Includes the concurrency edge case from spec.md Edge Cases: start a `GET /firmware-compliance` request, fire a `firmware_catalog_controller.reload()` mid-flight, assert the original request completes against its pre-reload snapshot (no partial mix of old + new targets observed)
- [ ] T070 [P] Performance smoke: assert SC-001 (`firmware-compliance` p95 < 250 ms over 5_000 devices × 200 targets), SC-006 (`upgrade-paths` p95 < 50 ms over 500 edges × 200 platforms), and SC-002 (full reload-from-disk → first request observing the new state in < 60 s for a synthetic 1,000-file catalog, measured wall-clock from `firmware_catalog_controller.reload()` invocation to `GET /firmware/targets` reflecting the new row). Synthetic dataset generator + `pytest.mark.perf` marker (excluded from default `pytest -q`, included in CI nightly)
- [ ] T071 [P] Update `README.md` + `deploy/README.md` + `specs/002-firmware-catalog/quickstart.md`: add the F2 quickstart (load YAML → reload → query compliance → upload blob); show the `make seed` + `make reset` flow producing the F1+F2 demo state
- [ ] T072 [P] Update `ROADMAP.md`: F2 status → "implemented", check the boxes per spec.md SC-001…SC-008
- [ ] T073 Run `/speckit-analyze` cross-artefact consistency pass on `specs/002-firmware-catalog/`; fix any drift it surfaces
- [ ] T074 Run full local CI: `make test` (ruff format --check + ruff check + mypy --strict + pytest -q --cov=gard --cov-fail-under=80). Fix any failures; do not push red

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No external dependencies. T001–T005 can run in parallel
- **Foundational (Phase 2)**: Depends on Setup. Within Phase 2: T006 (migration) must complete before T007–T013 (models) but T013 itself depends on all model files existing; T015/T017 depend on T015 of blob_store protocol; T018 depends on T017's runtime-schema copies; T019 depends on T008–T013 + T018; T020 depends on T019
- **User Stories (Phase 3+)**: All depend on Phase 2 completion. Within the F2 design, US1 + US2 are the joint MVP and should land first (in either order). US3, US4, US5 are independent of each other and can be parallelised
- **Polish (Phase 8)**: Depends on all desired user stories complete

### User Story Dependencies (within F2)

- **US1**: Reads from the catalog, never mutates. Depends only on Phase 2
- **US2**: Mutates the catalog via the loader, depends on Phase 2; the post-reload re-evaluation in T040 depends on US1's `compliance_controller.evaluate()` (T029)
- **US3**: Reads from the loader's output; depends on Phase 2. Independent of US1/US2
- **US4**: Adds the blob upload/download surface; depends on Phase 2 (`BlobStore`). Independent of US1/US2/US3 at the API level
- **US5**: Re-exposes US1/US3 over MCP. Functionally depends on US1 and US3 being implemented (the controllers it calls); the tool registration is independent

### Within Each User Story

- Tests MUST be written and FAIL before implementation (per the constitution + F1 ADR)
- Schemas before routers (Pydantic models flow into routers)
- Routers depend on their controllers
- Story complete before moving to next priority

### Parallel Opportunities

- Phase 1: T001–T005 all in parallel
- Phase 2 models (T007–T013) all in parallel after T006 lands
- Phase 2 utilities (T014, T015→T016, T017, T018, T021–T025) — most parallel; T015 blocks T016, T018 blocks T019, T019 blocks T020
- US1 vs US2 vs US3 vs US4 implementation (T029–T032 vs T037–T042 vs T048–T052 vs T056–T059) can run in parallel after Phase 2
- All test files marked [P] inside a story phase run in parallel

---

## Implementation Strategy

### MVP First (US1 + US2 — the joint F2 MVP)

1. Complete Phase 1: Setup (ADR-0011, networkx dep, compose volume, fixtures)
2. Complete Phase 2: Foundational (migration, models, BlobStore, graph cache, loader, controller, RBAC, settings, CSV bump, envelope)
3. Complete Phase 3: US1 (compliance read)
4. Complete Phase 4: US2 (git-native target authoring + lifespan-boot reload + post-reload re-evaluation)
5. **STOP and VALIDATE**: walk every AC from spec.md US1 + US2; run `quickstart.md` steps 1–6; flip PR #2 from draft to ready

### Incremental Delivery

1. MVP shipped (US1 + US2) → PR ready, CI green → merge to `main`
2. Add US3 (upgrade paths + prerequisites) → branch + PR → merge
3. Add US4 (blob storage) → branch + PR → merge
4. Add US5 (MCP tools) → branch + PR → merge
5. Polish (Phase 8) → final PR

### One-PR Delivery (autonomous run mode)

If running everything in one PR (this conversation's mode): land Phases 1–8 on `002-firmware-catalog`, push after each phase, mark PR ready at the end of Phase 4, leave the remaining phases as additional commits on the same PR. CI must stay green at every push.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [USn] label maps task to its user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or each logical group of [P] tasks
- Stop at any checkpoint to validate the story independently
- Avoid: vague tasks, same-file conflicts (especially in `app.py` router registration), cross-story dependencies that break independence

---

## Task Count Summary

- Phase 1 (Setup): 5 tasks (T001–T005)
- Phase 2 (Foundational): 20 tasks (T006–T025)
- Phase 3 (US1 — MVP): 7 tasks (T026–T032) — 3 test, 4 impl
- Phase 4 (US2 — MVP): 10 tasks (T033–T042) — 4 test, 6 impl
- Phase 5 (US3): 10 tasks (T043–T052) — 5 test, 5 impl
- Phase 6 (US4): 7 tasks (T053–T059) — 3 test, 4 impl
- Phase 7 (US5): 8 tasks (T060–T067) — 2 test, 6 impl
- Phase 8 (Polish): 7 tasks (T068–T074)

**Total: 74 tasks** across 8 phases. MVP checkpoint at the end of Phase 4 (T042) with 42 tasks complete.
