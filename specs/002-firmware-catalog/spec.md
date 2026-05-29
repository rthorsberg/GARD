# Feature Specification: Firmware Catalog

**Feature Branch**: `002-firmware-catalog`
**Created**: 2026-05-29
**Status**: Draft
**Input**: User description: "F2 — firmware catalog: `FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule`; YAML loader (lifecycle-as-code) + read APIs; git-native approval (PR-as-approval); SHA-256 checksum verification including optional uploaded blobs; MCP tools `get_target_firmware`, `get_upgrade_path` (+ list tools). Introduces device lifecycle transitions `classified → target_defined → compliant | outside_target`; ships the thin compliance boolean only — F3 layers drift taxonomy on top."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator sees which devices are on their firmware target (Priority: P1)

A network operations engineer needs to know, for every device GARD has classified, **what firmware version it should be running** and **whether it actually is**. The answer must be explainable: it cites the policy (target), the observed state, and the matching rule.

**Why this priority**: This is the smallest useful slice of compliance. Without it, F1's classified devices are inert — they have a vendor and a platform family but no "where should this be?" baseline. Every subsequent feature (F3 drift, F4 readiness, F5 uplift) depends on this answer existing.

**Independent Test**: After loading a `FirmwareTarget` YAML covering Cisco IOS XR + Juniper Junos and re-importing the F1 device fixture, calling `GET /api/v1/devices/{id}/firmware-compliance` returns `state=compliant` for the device whose observed firmware matches its target, `state=outside_target` for one that doesn't, and `state=unknown` for a device with no observed firmware. Each response cites the resolved target by id and the matched rule.

**Acceptance Scenarios**:

1. **Given** a `FirmwareTarget` YAML declares `target_version=7.5.2` for `platform_family=iosxr` with `scope_selector: region_in=[oslo]`, **And** device `r1.oslo` has `observed_firmware=7.5.2` and `region=oslo`, **When** the operator calls `GET /api/v1/devices/{r1.oslo.id}/firmware-compliance`, **Then** the response returns `state=compliant`, `target_ref=<target-id>`, `target_version=7.5.2`, `observed_version=7.5.2`, and a non-empty `correlation_id`.
2. **Given** the same target, **And** device `r2.oslo` has `observed_firmware=7.4.1`, **When** the operator calls the same endpoint, **Then** the response returns `state=outside_target` with `target_version=7.5.2`, `observed_version=7.4.1`, and `reasons[0].kind=version_mismatch`.
3. **Given** a device with `observed_firmware=null`, **When** the endpoint is called, **Then** the response returns `state=unknown` with `reasons[0].kind=missing_observation` and never coerces the missing value to a default.
4. **Given** a device that matches **no** target's `scope_selector`, **When** the endpoint is called, **Then** the response returns `state=target_defined=false` with `reasons[0].kind=no_target_matched`. The device's `lifecycle_state` remains `classified`.
5. **Given** the catalog is empty, **When** the endpoint is called for any device, **Then** the response returns `state=unknown` with `reasons[0].kind=empty_catalog`. No 5xx is emitted.

---

### User Story 2 — Operator publishes a new firmware target via PR (Priority: P1)

A platform engineer needs to define the firmware policy for a class of devices. The policy must be **reviewable in Git**, **takeable-down via revert**, and **anchored in the audit trail by commit SHA** — no hidden in-app state, no "who approved this in the UI?" archaeology.

**Why this priority**: The catalog is the policy. If operators can't reliably author, review, approve, and roll back policy, the whole compliance story is built on sand. This is what makes the constitution's "Lifecycle-as-Code" principle real for firmware.

**Independent Test**: After committing a new YAML file to `gard-catalog/firmware/targets/cisco-iosxr-edge.yaml` and triggering a catalog reload (CLI or app boot), `GET /api/v1/firmware/targets` lists the new target. An `AuditEvent` row carries the git commit SHA that introduced the file. Reverting the commit and reloading removes the target from the API and emits a corresponding retraction audit event.

**Acceptance Scenarios**:

1. **Given** a well-formed YAML file is placed under `gard-catalog/firmware/targets/`, **When** `gard catalog reload firmware` runs, **Then** the file is parsed, validated against the JSON Schema, upserted into `firmware_targets`, and one `AuditEvent` row is emitted with `action=firmware_catalog.target.loaded` and `after.git_commit_sha=<HEAD-sha>`.
2. **Given** a malformed YAML file (missing required field, unknown predicate, schema violation), **When** the reload runs, **Then** the entire reload **rolls back** (no partial upsert), the API returns the previously loaded catalog unchanged, and the loader exits non-zero with the offending file path and a human-readable reason. One `AuditEvent` with `action=firmware_catalog.reload_failed` is emitted.
3. **Given** a previously loaded target's YAML file is deleted from disk, **When** the reload runs, **Then** the target row is removed from `firmware_targets` (or marked `removed_at=<now>` — see Assumptions), an `AuditEvent` `firmware_catalog.target.removed` is emitted, and any device whose lifecycle was driven by that target re-enters `classified`.
4. **Given** the catalog is loaded, **When** the operator calls `GET /api/v1/firmware/targets`, **Then** the response lists each target with `id`, `scope_selector`, `platform_family`, `target_version`, `loaded_from_git_sha`, and `loaded_at`.

---

### User Story 3 — Operator queries upgrade paths and prerequisites (Priority: P2)

When planning an upgrade, an operator (or an MCP-mediated agent) needs to know **how to get from version X to version Y** on a given platform, and **what conditions must hold on the device** before the upgrade can proceed. Both questions must be answerable without executing anything.

**Why this priority**: Necessary for F4 readiness and F5 uplift planning. Ships in F2 because the data model and grammar belong with the rest of the catalog, even though no automated readiness verdict is rendered until F4.

**Independent Test**: After loading `gard-catalog/firmware/upgrade-paths/cisco-iosxr.yaml` declaring edges `7.4.1 → 7.5.2 → 7.8.1` (and an alternate edge `7.4.1 → 7.8.1` weighted higher), calling `GET /api/v1/firmware/upgrade-paths?platform_family=iosxr&from=7.4.1&to=7.8.1` returns the shortest chain `[7.4.1, 7.5.2, 7.8.1]`. Loading a prerequisite rule `min_disk_mb=2048` and calling `GET /api/v1/firmware/prerequisites` returns the rule with its `applies_to` selector.

**Acceptance Scenarios**:

1. **Given** an `UpgradePath` catalog declares edges A→B (weight 1), B→C (weight 1), A→C (weight 5), **When** the operator queries `GET /api/v1/firmware/upgrade-paths?platform_family=X&from=A&to=C`, **Then** the response returns the chain `[A, B, C]` with `total_weight=2` and `hop_count=2`, **not** the direct edge.
2. **Given** no path exists between two versions, **When** the operator queries, **Then** the response returns HTTP 200 with `chain=[]`, `total_weight=null`, and `reasons[0].kind=no_path`. Never a 404 — the operator distinguishes "no path" from "endpoint missing".
3. **Given** a `PrerequisiteRule` carries predicate `min_disk_mb=2048`, **When** the loader runs, **Then** the rule is upserted and JSON-Schema-validated. An unknown predicate kind (e.g. `secret_handshake`) causes the rule's file to fail validation and rolls the entire reload back.
4. **Given** a `PrerequisiteRule` declares `tagged_with: [edge]`, **When** the loader runs, **Then** the rule is **accepted** (schema validates) but recorded with `evaluable=false` and a `reasons[0].kind=predicate_deferred` annotation, because Device tags are not yet a thing until F7 (NetBox). The rule appears in `GET /api/v1/firmware/prerequisites` with this annotation.

---

### User Story 4 — Operator uploads and downloads a verified firmware package (Priority: P2)

A firmware engineer needs to attach the actual installer artefact to a `FirmwarePackage` catalog entry, so downstream features (uplift waves in F5) can hand the file to an execution adapter. GARD must verify the SHA-256 declared in the YAML against the bytes it stores, and verify again on every download.

**Why this priority**: Decoupled from US1–US3 — compliance and target resolution work fine without a stored blob. Operators only need this when the v1 deployment is a true "ship the artefact too" deployment. Listed P2 to make the MVP clearer: ship US1+US2 without blob storage and the feature is already useful.

**Independent Test**: Upload a 100 MB binary via `POST /api/v1/firmware/packages/{id}/blob` whose body's SHA-256 matches the catalog YAML's `sha256` field. The upload returns 200 with the computed checksum. A subsequent `GET .../blob` returns the bytes; tampering with the stored blob (test-only manipulation) causes the next GET to return HTTP 500 with `code=blob_checksum_mismatch` and an audit event.

**Acceptance Scenarios**:

1. **Given** a `FirmwarePackage` catalog entry declares `sha256=<hex>` and `byte_size=<n>`, **When** the operator uploads a file whose bytes hash to `<hex>` via `POST /api/v1/firmware/packages/{id}/blob`, **Then** the response returns 200 with `computed_sha256=<hex>`, `bytes_written=<n>`, an `AuditEvent` `firmware_catalog.package.blob_stored` is emitted, and a `LifecycleEvidence` row records the upload with the same checksum.
2. **Given** an upload whose computed SHA does **not** match the declared `sha256`, **When** the operator submits, **Then** the server returns HTTP 422 with `code=blob_checksum_mismatch`, no bytes are persisted, and one `AuditEvent` records the rejection.
3. **Given** an upload exceeding the configured size cap, **When** the operator submits, **Then** the server returns HTTP 413 with `code=blob_too_large` after streaming and discarding bytes up to the cap. No partial blob is left behind.
4. **Given** a stored blob, **When** the operator calls `GET .../blob`, **Then** the server streams the bytes while recomputing the SHA. On match, it sets `Content-Length` and `X-GARD-SHA256` headers and returns 200. On mismatch (corrupted storage), it returns HTTP 500 with `code=blob_checksum_mismatch_on_read` and emits an audit event so the corruption is investigable.
5. **Given** a `FirmwarePackage` catalog entry exists but no blob has been uploaded, **When** the operator calls `GET .../blob`, **Then** the response returns HTTP 404 with `code=blob_not_present`. This is **not** an error condition for catalog operations.

---

### User Story 5 — MCP-mediated agent answers firmware questions (Priority: P3)

An MCP client (LLM-driven assistant, support agent's chat tool) asks the system: "Which devices in Oslo are not on their target firmware?" and "How would I get a Cisco IOS XR box from 7.4.1 to 7.8.1?". The answers must come **only** through the curated MCP tool surface — no raw SQL, no shell, no arbitrary HTTP.

**Why this priority**: P3 because it's strictly a re-skinning of the read APIs over the MCP transport. Skippable for the MVP; valuable for the demo and for the constitution principle that MCP exposes curated tools, not infrastructure.

**Independent Test**: An MCP client invokes `get_target_firmware(device_id=<r2.oslo-id>)` and receives a structured response matching the REST endpoint's body. Calling `get_upgrade_path(platform_family=iosxr, from=7.4.1, to=7.8.1)` returns the same chain as the REST query. Invoking any tool **outside** the F2 disallowed-list (e.g. `execute_sql`, `read_file`) is rejected by the MCP server.

**Acceptance Scenarios**:

1. **Given** the F2 MCP server is running, **When** an authenticated MCP client lists tools, **Then** it sees exactly: `get_target_firmware`, `get_upgrade_path`, `list_firmware_targets`, `list_firmware_packages`, `list_upgrade_paths` (in addition to F1's `list_devices` and `get_device_lifecycle_status`).
2. **Given** an MCP client invokes `get_target_firmware(device_id=<id>)`, **When** the tool resolves, **Then** the response payload matches the body of `GET /api/v1/devices/{id}/firmware-compliance` field-for-field, with the same `correlation_id` propagated through the audit pipeline.
3. **Given** an MCP client attempts a tool **not** on the published list, **When** the server receives the call, **Then** it returns the MCP error envelope `code=tool_not_found` and emits an `AuditEvent` `mcp.disallowed_tool_attempt` with the client identity.
4. **Given** an MCP client lacks `READ_FIRMWARE_CATALOG`, **When** it invokes any of the five F2 tools, **Then** the server returns the MCP error envelope `code=forbidden` and emits an `AuditEvent` `auth.denied`.

---

### Edge Cases

- **Catalog reload during a live request**: if a reload commits while an in-flight `firmware-compliance` request is mid-resolution, the request must complete against a consistent catalog snapshot (the one it started with) and not observe a partial mix of old + new targets.
- **Multiple targets match a device**: a device matches more than one `FirmwareTarget`'s `scope_selector`. The resolution must be deterministic and explainable. Default: most-specific selector wins (e.g. `region_in=[oslo] AND vendor=cisco` beats `vendor=cisco`); ties broken by `loaded_at` descending. The response cites the **runner-up** targets so the operator sees the precedence outcome.
- **CSV import with stale firmware data**: if a device is re-imported with a newer `observed_firmware` value, the compliance result must reflect the new observation on the next read. No stale-cache window.
- **Device deleted after target evaluation**: if a device is removed (future feature) while its compliance row is materialised, subsequent reads return HTTP 404; the materialised state is invalidated rather than orphaned.
- **`UpgradePath` graph contains a cycle**: e.g. someone declares A→B and B→A both weighted 1. Pathfinding must terminate and choose the shortest acyclic path; cycles are logged but not rejected at load (catalog stays loadable).
- **Same SHA-256 declared by two packages**: at most one package per `(vendor, platform_family, version)` may declare a given checksum. Conflicts cause the loader to reject the second file with a clear error.
- **Catalog file declares a target version with no matching package**: this is **allowed**. Targets are policy; packages are artefacts. A target without a package means "this is the goal, get the file from the vendor yourself". Compliance evaluation still works; only blob download is unavailable.
- **A `not_in_state` predicate references a state that doesn't exist** (typo, future state name): rule fails JSON Schema validation against the enumerated `LifecycleState` enum and the entire reload rolls back.
- **Concurrent uploads to the same package**: only one upload succeeds; the loser receives HTTP 409 `code=blob_upload_in_progress`.
- **Operator queries upgrade path with `from == to`**: returns the zero-hop chain `[X]` with `total_weight=0`, `hop_count=0`, no `reasons` entries.

## Requirements *(mandatory)*

### Functional Requirements

#### Catalog entities and YAML source-of-truth

- **FR-001**: System MUST define four catalog entity kinds: `FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule`. Each kind has a JSON-Schema (2020-12) that the loader validates every file against before persistence.
- **FR-002**: The on-disk YAML tree under `gard-catalog/firmware/{targets,packages,upgrade-paths,prerequisites}/` MUST be the authoritative source of catalog state. The database table is a read-through cache rebuilt by the loader.
- **FR-003**: The catalog loader MUST be transactional: either every file in a reload succeeds and the resulting state is committed atomically, or no change to the database occurs.
- **FR-004**: The loader MUST record, on every loaded row, the git commit SHA of the file's last change (`loaded_from_git_sha`) and the wall-clock time of the load (`loaded_at`). Both are returned in API responses.
- **FR-005**: Removing a file from disk and re-running the loader MUST remove the corresponding row from the active catalog (soft-delete via `removed_at` is acceptable — see Assumptions) and emit a retraction audit event.
- **FR-006**: The loader MUST be invokable from three places: (a) on application start, as part of the existing lifespan handler; (b) via `gard catalog reload firmware` on the CLI; (c) implicitly on the existing `gard catalog reload` command, which now reloads both normalization and firmware catalogs in one transaction.
- **FR-007**: The loader MUST refuse to overwrite an existing row with conflicting natural-key identity from a different file (e.g. two different files claiming the same `(vendor, platform_family, version)` for a `FirmwarePackage`). Conflicts roll the entire reload back.

#### Firmware target resolution and the thin compliance boolean

- **FR-008**: A `FirmwareTarget` MUST declare a `scope_selector` (a structured predicate over Device facts), `platform_family`, and `target_version`. Optionally: `valid_from`, `valid_until`, `notes`.
- **FR-009**: Given a Device with classified facts, the target-resolution controller MUST evaluate every `FirmwareTarget`'s `scope_selector` against the device's facts and select the **most specific** match. Specificity is defined deterministically as the count of constraints in the selector; ties broken by `loaded_at` descending.
- **FR-010**: The system MUST introduce three new device lifecycle states reachable from `classified`: `target_defined`, `compliant`, `outside_target`. The state machine MUST be:

  ```
  classified ──(target resolved)──▶ target_defined
  target_defined ──(observed == target)──▶ compliant
  target_defined ──(observed != target)──▶ outside_target
  target_defined ──(observation missing)──▶ unknown  (terminal until next observation)
  ```

  Transitions back to `classified` MUST occur when the resolved target is removed from the catalog. Transitions out of `target_defined`/`compliant`/`outside_target` MUST occur when the device's `observed_firmware` changes.
- **FR-011**: The system MUST expose `GET /api/v1/devices/{id}/firmware-compliance` returning an envelope with `state`, `summary`, `target_ref`, `target_version`, `observed_version`, `reasons[]`, `confidence`, `as_of`, `correlation_id`. The shape matches the F1 envelope contract from ADR-0005.
- **FR-012**: The compliance response MUST cite, in `reasons`, the matched target (`kind=target_matched`, `ref=<target-id>`), the version comparison outcome (`kind=version_match` or `kind=version_mismatch`), and any runner-up targets that lost the specificity tiebreaker (`kind=target_runner_up`).
- **FR-013**: When the device's `observed_firmware` is `null`, the compliance response MUST return `state=unknown` with `reasons[0].kind=missing_observation` and MUST NOT coerce the observation to a default.
- **FR-014**: When no target's `scope_selector` matches the device, the compliance response MUST return `state=classified` (no transition occurs) with `reasons[0].kind=no_target_matched`.

#### Upgrade-path graph

- **FR-015**: An `UpgradePath` MUST declare a directed edge `(from_version, to_version)` for a given `platform_family`, with an optional integer `weight` (default `1`). The catalog file MAY contain multiple edges.
- **FR-016**: The system MUST expose `GET /api/v1/firmware/upgrade-paths?platform_family=...&from=...&to=...` which performs a shortest-weight-sum traversal over the edge graph and returns `chain: [v1, v2, ..., vN]`, `hop_count`, `total_weight`.
- **FR-017**: When no path exists between `from` and `to`, the endpoint MUST return HTTP 200 with `chain=[]`, `total_weight=null`, and `reasons[0].kind=no_path`. HTTP 404 is reserved for "platform family not found in catalog".
- **FR-018**: When `from == to`, the endpoint MUST return `chain=[from]`, `hop_count=0`, `total_weight=0`, `reasons=[]`.
- **FR-019**: The graph traversal MUST handle cycles defensively (visited-set algorithm) and MUST NOT crash, infinite-loop, or stack-overflow on adversarial input.

#### Prerequisite rules

- **FR-020**: A `PrerequisiteRule` MUST declare an `applies_to` selector (same shape as `FirmwareTarget.scope_selector`), a `predicate` (one of the enumerated kinds below), and a `severity` (`required`, `recommended`).
- **FR-021**: The system MUST support exactly the following predicate kinds in v1: `min_ram_mb`, `min_disk_mb`, `min_current_version`, `hardware_revision_in`, `license_present`, `intermediate_version_required`, `not_in_state`, `region_in`, `tagged_with`.
- **FR-022**: Predicates `min_ram_mb`, `min_disk_mb`, `license_present` reference new Device facts (`ram_mb: int|null`, `disk_mb: int|null`, `licenses: list[str]|null`) that MUST be added to the Device model in this feature.
- **FR-023**: The CSV import schema MUST bump to `csv_schema_version: 1.1.0`, adding three optional columns: `ram_mb`, `disk_mb`, `licenses` (the latter as a semicolon-separated list). CSVs claiming `1.0.0` MUST still load successfully (back-compat).
- **FR-024**: The `tagged_with` predicate MUST be accepted by the loader (schema-valid) but MUST be evaluated as `unknown` with `reasons[0].kind=predicate_deferred` until a Device-tag source is wired up. F2 ships the predicate vocabulary; the evaluator returns "unknown" rather than rejecting it.
- **FR-025**: The system MUST expose `GET /api/v1/firmware/prerequisites` listing all loaded prerequisite rules with their `applies_to`, `predicate`, `severity`, `evaluable` flag (`false` only for deferred predicates), and `loaded_from_git_sha`.
- **FR-026**: Prerequisite **evaluation** against specific devices is **out of scope for F2**. The rules are loaded and queryable; F4 (Readiness & Prerequisites) consumes them to render verdicts.

#### Firmware package metadata and optional blob

- **FR-027**: A `FirmwarePackage` MUST declare `vendor`, `platform_family`, `version`, `sha256`, `byte_size`, `signed_by` (the vendor signing identity, e.g. `cisco`), and optionally `release_date`, `download_url`, `notes`.
- **FR-028**: The system MUST expose `GET /api/v1/firmware/packages` and `GET /api/v1/firmware/packages/{id}` returning the catalog metadata. Both endpoints are read-only and grant access via the `READ_FIRMWARE_CATALOG` permission.
- **FR-029**: The system MUST expose `POST /api/v1/firmware/packages/{id}/blob` accepting a streamed binary upload. The handler MUST compute SHA-256 chunked during write, compare against the catalog's declared `sha256`, and persist only on match. Mismatches MUST return HTTP 422 with `code=blob_checksum_mismatch` and zero persistence.
- **FR-030**: The system MUST expose `GET /api/v1/firmware/packages/{id}/blob` which streams the stored bytes while recomputing the SHA. On match: HTTP 200 + `X-GARD-SHA256` header. On mismatch: HTTP 500 with `code=blob_checksum_mismatch_on_read` + an audit event. When no blob is present: HTTP 404 with `code=blob_not_present`.
- **FR-031**: The system MUST enforce a configurable per-upload size cap (`GARD_FIRMWARE_BLOB_MAX_BYTES`, default `5_368_709_120` = 5 GiB). Uploads exceeding the cap stream-and-discard up to the cap, then return HTTP 413 with `code=blob_too_large`.
- **FR-032**: Blob storage MUST be accessed through a `BlobStore` protocol with one concrete v1 implementation, `LocalFsBlobStore`, rooted at `GARD_BLOB_ROOT` (default `/var/lib/gard/blobs/`). A future S3-backed implementation is explicitly out of scope but the protocol is the seam.
- **FR-033**: Concurrent uploads to the same package MUST be serialised: only one writer may hold the package's blob path at a time. Losers MUST receive HTTP 409 with `code=blob_upload_in_progress`.

#### MCP tool surface

- **FR-034**: The MCP server MUST expose exactly five new tools in F2: `get_target_firmware(device_id)`, `get_upgrade_path(platform_family, from_version, to_version)`, `list_firmware_targets(filter?)`, `list_firmware_packages(filter?)`, `list_upgrade_paths(platform_family?)`. All are read-only.
- **FR-035**: Each MCP tool's input and output schemas MUST be bounded — no free-form strings beyond the F1 envelope shape, all list responses MUST cap at the existing `MCP_LIST_MAX_RETURN` setting from F1.
- **FR-036**: The MCP server MUST reject any tool invocation outside the published F1+F2 tool list with `code=tool_not_found` and emit `AuditEvent` `mcp.disallowed_tool_attempt`.
- **FR-037**: All five F2 MCP tools MUST flow through the same auth/RBAC dependency as F1 and emit identical audit records to their REST equivalents, with the `correlation_id` carried through.

#### Auth, audit, evidence

- **FR-038**: Two new permissions MUST be introduced: `READ_FIRMWARE_CATALOG` (granted to `viewer`, `lifecycle_manager`, `mcp_client`, `system_admin`) and `MANAGE_FIRMWARE_BLOB` (granted to `lifecycle_manager`, `system_admin`). No `MANAGE_FIRMWARE_CATALOG` permission exists — catalog mutation is by `git push`, not by role.
- **FR-039**: Catalog loads MUST emit an `AuditEvent` per loaded/removed file with `action` in `{firmware_catalog.target.loaded, firmware_catalog.target.removed, firmware_catalog.package.loaded, …, firmware_catalog.reload_failed}` and `after.git_commit_sha` populated.
- **FR-040**: Every successful blob upload MUST emit a `LifecycleEvidence` row with `evidence_type=firmware_package_upload`, `subject_type=FirmwarePackage`, `source_checksum=<sha256>`, and the actor recorded.
- **FR-041**: Every target-resolution outcome (transition into `target_defined`, `compliant`, `outside_target`, or back to `classified`) MUST emit one `AuditEvent` `firmware_target.compliance_evaluated` with `before`/`after` state and the resolved target id.
- **FR-042**: The append-only DB role established in F1 MUST continue to be unable to UPDATE or DELETE `audit_events` and `lifecycle_evidence` rows. F2 introduces no exemption.

#### Operational

- **FR-043**: The Docker Compose stack MUST expose `GARD_BLOB_ROOT` as a configurable volume mount. The default dev mount is a named volume `deploy_gard-blobs` separate from the Postgres volume.
- **FR-044**: The `make seed` target MUST be extended to optionally seed firmware catalog YAML fixtures alongside the device fixture, so `make reset` continues to produce a fully populated dev environment for both F1 and F2 features.
- **FR-045**: The `/healthz` endpoint MUST verify, in addition to F1's checks, that the blob root is writable when the API role expects to write there (i.e. when `MANAGE_FIRMWARE_BLOB` is reachable). Failures degrade the health response to `status=degraded`, not `unhealthy`.

### Key Entities

- **FirmwareTarget**: A policy statement: "devices matching `scope_selector` on `platform_family` should be on `target_version`". Identity: hash of `(scope_selector, platform_family, target_version)`. References: the YAML file path it loaded from + the git SHA. Relationships: zero-or-more `Device` rows resolved against it at evaluation time (relationship is computed, not stored as FK in F2).
- **FirmwarePackage**: A concrete installer artefact for a specific `(vendor, platform_family, version)`. Identity: `(vendor, platform_family, version, sha256)`. May or may not have a stored blob. References: optional `BlobStore` key. Constitutional invariant: the declared SHA-256 in the YAML is the source of truth; no verification path may bypass it.
- **UpgradePath**: A single directed edge in the upgrade graph for one `platform_family`. Identity: `(platform_family, from_version, to_version)`. Carries an optional `weight`. The graph as a whole is the union of all edges.
- **PrerequisiteRule**: A rule whose left-hand side is `applies_to` (a Device-fact selector) and right-hand side is `predicate` (one of nine enumerated kinds). Carries a `severity` and an `evaluable` flag. F2 stores them; F4 evaluates them.
- **DeviceFacts (extended)**: Three optional new fields — `ram_mb: int|null`, `disk_mb: int|null`, `licenses: list[str]|null` — added in F2 to back the new prerequisite predicates. Optional, observation-driven, never coerced to defaults.
- **ScopeSelector**: A shared predicate language used by both `FirmwareTarget.scope_selector` and `PrerequisiteRule.applies_to`. Vocabulary: `vendor_normalized`, `platform_family`, `region_in`, `site_in`, `role_in`, `hardware_revision_in`, `not_in_state`, `tagged_with` (deferred). All conjunctive (AND); no disjunction in v1.
- **CatalogLoadEvent**: Logical (audit-only, no dedicated table) — an `AuditEvent` row of kind `firmware_catalog.*` recording every load/remove with the responsible git commit SHA. The auditable history of the catalog.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can answer "is device X on its firmware target?" via a single HTTP call returning in **under 250 ms p95** against a catalog of up to 200 targets and 5,000 devices. Compliance state is correct on the first read after CSV import (no stale-cache window).
- **SC-002**: A new firmware policy goes from "PR merged to `gard-catalog`" to "visible in the live API on every running instance" in **under 60 seconds**, without requiring a service restart or operator intervention beyond `git pull` + `gard catalog reload firmware` (or app boot).
- **SC-003**: 100% of catalog mutations are traceable to a git commit SHA in the audit log. An auditor reading the audit table for any 30-day window can reconstruct the complete sequence of catalog changes without consulting any external system.
- **SC-004**: A malformed YAML file in a reload **never** results in a partial catalog state. Across an adversarial test suite of at least 20 malformed inputs (missing fields, unknown predicates, schema violations, cyclic upgrade paths, duplicate identities), the live catalog state remains exactly the pre-reload state in 100% of cases.
- **SC-005**: A `FirmwarePackage` blob's integrity is verified on every download. Tampering with a stored blob is detected on the next GET in 100% of cases. The hash on first write equals the hash on every subsequent read (modulo intentional re-upload).
- **SC-006**: `get_upgrade_path(from, to)` returns the shortest legal chain within **under 50 ms p95** over a graph of up to 500 edges and 200 platform families. No-path responses are distinguishable from missing-platform responses.
- **SC-007**: An MCP-mediated agent can answer "which Cisco IOS XR devices in Oslo are outside their target?" using **only** the published MCP tool surface, with the answer matching, byte-for-byte (after envelope normalisation), the equivalent answer composed from the REST endpoints. The transcript shows zero attempts to invoke disallowed tools.
- **SC-008**: The MVP (US1 + US2 only — compliance read + git-native target authoring) is operable end-to-end in **under 15 minutes** from a fresh clone, using `make reset && make seed` plus a single committed firmware target YAML file. Documented in `specs/002-firmware-catalog/quickstart.md` (planning phase artefact).

## Assumptions

- **Blob storage scope retraction is bounded**: F1's research D2 said "no object store in v1". F2 retracts that for firmware packages only — the `BlobStore` protocol is *not* used for evidence, audit, or any other artefact, and the local-filesystem implementation is the only v1 backend. F2's plan will record this as an explicit revision to D2 with rationale.
- **Soft-delete vs hard-delete on catalog removal**: catalog removals MAY be implemented as `removed_at IS NOT NULL` filters rather than physical row deletion. This preserves the audit chain across the row's lifetime. The API filters removed rows; the audit can still walk them. Final decision deferred to `plan.md`.
- **Loader anchors to the *file's last commit SHA*, not the worktree HEAD**: when the loader resolves the git SHA for a file, it uses `git log -1 --format=%H -- <file>` semantics, not HEAD. This means uncommitted local edits during dev DO load into the DB but with `loaded_from_git_sha=null` and a structured warning. Production deploys always operate against a clean tree.
- **No catalog ingest from Diode / NetBox in v1**: the constitution and ADR-0001 keep NetBox as identity source, not catalog source. Firmware catalog ingest in v1 is exclusively from `gard-catalog/firmware/` on disk. F7 may later add a NetBox read path for inventory facts (RAM/disk discovery), but not for firmware policy.
- **Upgrade-path graphs are small**: v1 assumes well under 10,000 edges per platform family. Dijkstra over an in-memory adjacency list is fast enough; no need for precomputed shortest-path tables. If we ever exceed that, F2's plan can introduce a materialised `firmware_upgrade_paths_computed` cache; out of scope here.
- **Prerequisite evaluation is F4's problem**: F2 ships the rule vocabulary, JSON Schema, loader, and list API. The `evaluate_prerequisites(device_id)` controller — and any UI for readiness verdicts — lands in F4.
- **CSV schema is back-compatible**: v1.0.0 CSVs continue to load against the v1.1.0 schema; the three new columns default to `null`. The version bump is forward-looking metadata, not a breaking change. The schema YAML in `specs/001-device-import-normalize/contracts/csv-schema.yaml` will be amended (additive only) in `plan.md`'s contracts phase.
- **`tagged_with` is documented but inert**: F2 ships the predicate vocabulary so policy authors can write rules **today** that will become evaluable when F7's NetBox tag source arrives. The current evaluator returns `unknown` with `predicate_deferred`. This is preferable to "predicate doesn't exist" because it lets the operator draft policy ahead of the data source.
- **Multi-target ties are deterministic**: when two targets are equally specific, `loaded_at DESC` breaks the tie. This is implementation-defined but documented and stable; operators can rely on it.
- **Single MCP transport**: F2 reuses F1's Streamable HTTP MCP transport. No new transport surface; no stdio.
- **No catalog-mutation MCP tools in F2**: deferred to F5 (uplift planning). MCP in F2 is purely read.
- **App-boot reload is idempotent**: re-running the loader against an unchanged tree MUST be a no-op (zero audit rows emitted). Only state changes produce audit rows. This is what makes `make reset` viable.
