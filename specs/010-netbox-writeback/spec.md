# Feature Specification: NetBox Lifecycle Write-Back

**Feature Branch**: `010-netbox-writeback`
**Created**: 2026-06-01
**Status**: Draft
**Input**: User description: "F10 — NetBox write-back: after F7 read sync and F9 device-type bootstrap, GARD pushes lifecycle metadata to NetBox custom fields and tags for all NetBox-linked devices. Trigger: post-sync. Scope: generic for all synced devices. Both custom fields and tags."

## Why this feature exists

F7 established GARD as a **read-only consumer** of NetBox identity (ADR-0017). F9 ensured NetBox holds **community-aligned device types** so DCIM shape is credible. Operators can now sync inventory into GARD and run compliance, readiness, and uplift — but **NetBox operators still cannot see GARD lifecycle conclusions** where they already work (NetBox UI, reports, Assurance-adjacent workflows).

F10 closes that gap for **metadata only**: GARD writes **lifecycle-derived** custom field values and tags back to NetBox devices that GARD has linked — without mutating DCIM identity (hostname, serial, site, device type, rack placement).

> *NetBox continues to own infrastructure identity and placement. GARD continues to own firmware lifecycle truth. F10 publishes a read-only-for-humans **mirror** of GARD lifecycle status into NetBox so operators see one pane of glass.*

F10 does **not** create or delete NetBox devices, change device types, or import firmware observations from NetBox.

## User decisions (from kickoff)

| Topic | Decision |
|-------|----------|
| NetBox targets | **Both** custom fields and tags |
| Trigger | **Post-sync** — write-back runs automatically after a successful NetBox sync completes |
| Device scope | **Generic** — all NetBox-linked devices reconciled in the sync run (not limited to ISR1121 or a single vendor) |

## Clarifications

### Session 2026-06-01

- Q: When write-back partially fails, what HTTP status should sync return? → A: **Phased success (200)** — sync pull success returns 200; write-back outcomes reported in response body; partial write-back failure does not change HTTP status.
- Q: Who provisions NetBox custom fields required by write-back? → A: **Dev bootstrap, prod manual** — dev/lab script creates custom fields (and tag definitions if needed) from manifest; production operators provision manually; missing fields → per-device `failed`.
- Q: Which devices receive write-back each sync run? → A: **Full sync batch** — all NetBox-linked devices processed in the sync run, not only devices created/updated during reconciliation.
- Q: Tag conflict policy when operators edit NetBox tags? → A: **Reconcile tags** — GARD syncs manifest tag slugs (add/remove); conflict reporting applies to custom fields only.
- Q: Should sync auto-run compliance/readiness before write-back? → A: **No auto-eval** — write-back uses current stored GARD evaluations; sync does not trigger compliance/readiness evaluation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lifecycle metadata appears in NetBox after sync (Priority: P1)

A platform engineer runs NetBox sync. GARD pulls device identity (F7), reconciles `Device` rows, then **automatically** pushes current lifecycle metadata to each linked NetBox device: configured custom fields (e.g., lifecycle state, drift summary, readiness summary, target firmware, last evaluated time) and canonical GARD tags (e.g., reflecting drift or readiness posture). She opens the device in NetBox and sees GARD fields populated without a separate manual export step.

**Why this priority**: This is the core operator value — lifecycle visibility in NetBox immediately after sync.

**Independent Test**: With two NetBox-linked ISR1121 devices that have compliance/readiness evaluations in GARD, one successful sync updates both NetBox device records with expected custom field values and tag slugs; a write-back section in the sync report shows `updated=2`, `skipped=0`, `failed=0`.

**Acceptance Scenarios**:

1. **Given** a GARD device with `netbox_device_id` and fresh compliance/readiness evaluations, **When** sync completes successfully, **Then** the corresponding NetBox device receives updated custom field values defined in the GARD write-back manifest.
2. **Given** the same device, **When** write-back runs, **Then** canonical GARD lifecycle tags on the NetBox device reflect current GARD posture (tags added/removed idempotently; no duplicate tag assignments).
3. **Given** a device was created in GARD from NetBox during sync (`source_system=netbox`) but has no evaluations yet, **When** write-back runs, **Then** NetBox receives explicit **unknown / not evaluated** sentinel values (not blank omission) for evaluation-derived fields.
4. **Given** sync fails or rolls back (e.g., NetBox unreachable during pull), **When** the operator receives the error response, **Then** no write-back phase runs and NetBox is unchanged by GARD.

---

### User Story 2 - Write-back manifest governs field mapping (Priority: P1)

A catalog maintainer updates which GARD lifecycle facts are published to NetBox by editing a **version-controlled write-back manifest** (lifecycle-as-code): custom field keys, tag slugs, and mapping from GARD lifecycle concepts to NetBox-facing labels. Validation fails before any NetBox write if a manifest entry references an undefined field or duplicate tag slug.

**Why this priority**: Per-deployment NetBox custom field names differ; GARD must not hard-code operator-specific strings in application code.

**Independent Test**: Manifest lists at least lifecycle state, drift summary, readiness summary, and target firmware; contract tests validate schema; dry-run mode validates manifest without NetBox writes.

**Acceptance Scenarios**:

1. **Given** the write-back manifest, **When** validation runs, **Then** every mapped custom field and tag slug is unique and every GARD source attribute is an allowed lifecycle field.
2. **Given** an operator adds a new tag mapping to the manifest, **When** write-back runs after sync, **Then** only manifest-listed tags are managed by GARD (GARD does not remove unrelated NetBox tags).
3. **Given** a NetBox instance missing a required custom field definition, **When** write-back runs, **Then** the device is reported `failed` with a clear reason; other devices in the batch still process.
4. **Given** a dev/lab NetBox stack, **When** the operator runs the documented write-back bootstrap step before first sync, **Then** all manifest-declared custom fields (and required tag objects) exist in NetBox without manual UI setup.

---

### User Story 3 - Conflict-safe, idempotent updates (Priority: P2)

An operator re-runs sync on an estate where NetBox devices already carry GARD metadata from a prior run. Write-back updates only changed values; a second sync with unchanged GARD evaluations produces skip counts, not duplicate tags or spurious PATCH traffic. If an operator manually edited a GARD-managed custom field in NetBox to a different value since last sync, GARD reports a **conflict** for that device and does not silently overwrite unless an explicit override policy is enabled (default: skip and report).

**Why this priority**: Dual-writer ambiguity was the reason F7 stayed read-only; F10 must not reintroduce silent data loss.

**Independent Test**: Two consecutive syncs with stable evaluations → second write-back report shows all entries `skipped` or `unchanged`; deliberate manual NetBox edit → next write-back reports `conflict`.

**Acceptance Scenarios**:

1. **Given** NetBox already has GARD metadata from a prior successful write-back, **When** sync and write-back run again with unchanged GARD evaluations, **Then** the write-back summary shows zero erroneous duplicates and no NetBox tag duplication.
2. **Given** an operator changed a GARD-managed custom field directly in NetBox, **When** write-back runs with default policy, **Then** that device appears in `conflicts[]` with expected vs actual values; GARD does not overwrite.
3. **Given** an operator removed a GARD-managed tag slug from a NetBox device, **When** write-back runs, **Then** GARD re-applies the tag if GARD posture still warrants it (tag reconciliation); this does **not** raise a field-style conflict.
4. **Given** GARD evaluation results changed since last write-back, **When** write-back runs, **Then** NetBox custom fields and tags update to reflect the new GARD truth.

---

### User Story 4 - Auditable write-back outcomes (Priority: P2)

Security and operations reviewers inspect what GARD changed in NetBox. Each sync run emits audit events for write-back start/completion (or failure) and includes per-device outcomes in the sync response. Evidence records capture the write-back summary counts and correlation id.

**Why this priority**: Write access to NetBox requires the same governance bar as other GARD mutations (Principle V).

**Independent Test**: After sync+write-back, audit log contains `netbox.writeback.started` and `netbox.writeback.completed`; evidence row exists with summary counts.

**Acceptance Scenarios**:

1. **Given** a successful sync with write-back, **When** audit events are queried, **Then** write-back lifecycle events appear with the same `correlation_id` as the sync run.
2. **Given** partial write-back failure (one device missing custom field), **When** the run completes, **Then** the HTTP response is **200** (sync pull succeeded), the sync response reports mixed write-back success with failed entries enumerated, and sync reconciliation results remain committed.

---

### Edge Cases

- **Device not NetBox-linked** (`netbox_device_id` null): Excluded from write-back; listed as `skipped_not_linked` in report.
- **Device linked but identity unchanged in sync**: Still included in write-back batch (lifecycle fields/tags may have changed in GARD since last run).
- **NetBox write token missing or read-only**: Write-back phase fails fast with a clear configuration error; sync pull results remain committed if sync phase already succeeded.
- **NetBox unreachable during write-back**: Sync API returns **200** (pull succeeded); sync report marks write-back phase failed or partial; operator can retry write-back without re-pulling (future convenience) or re-run sync.
- **Large estates**: Write-back respects the same device batch bounds as sync; per-device outcomes paginated in report summary counts.
- **Custom field type mismatch** (e.g., NetBox field is boolean, GARD sends text): Device marked failed; manifest validation should catch known type mismatches where possible pre-flight.
- **Tags shared with non-GARD workflows**: Only manifest-declared tag slugs are added/removed by GARD reconciliation; GARD never strips operator tags outside that allow-list.
- **Operator removes a GARD-managed tag**: Next write-back re-applies or removes tags to match current GARD posture (reconciliation); not reported as `conflict`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After a **successful** NetBox sync completes, GARD MUST automatically run a write-back phase for **every device processed in that sync run** that has a `netbox_device_id` — including devices whose identity was unchanged but lifecycle evaluations may have updated.
- **FR-001a**: Write-back MUST NOT trigger compliance or readiness evaluation; it MUST read the latest stored evaluation results (or unknown sentinels when absent) at post-sync time.
- **FR-002**: Write-back MUST update NetBox **custom fields** and **tags** according to a version-controlled write-back manifest (lifecycle-as-code).
- **FR-003**: Write-back MUST apply to **all NetBox-linked devices in scope** of the sync run — not limited to a single vendor, model, or fixture set.
- **FR-004**: Write-back MUST NOT create, delete, or relocate NetBox devices; MUST NOT modify DCIM identity fields (name, serial, site, device type, rack, position).
- **FR-005**: Write-back MUST be idempotent: repeated runs with unchanged GARD source data MUST NOT duplicate tags or produce redundant updates.
- **FR-006**: When GARD evaluation data is absent for a linked device, write-back MUST publish explicit unknown/not-evaluated sentinel values for evaluation-derived custom fields.
- **FR-007**: When a GARD-managed NetBox **custom field** value differs from what GARD would write (manual operator edit), write-back MUST report a **conflict** and MUST NOT overwrite by default.
- **FR-007a**: GARD-managed **tags** declared in the manifest MUST be reconciled each write-back (add when warranted, remove when no longer warranted); manual tag removal MUST NOT produce a custom-field-style conflict.
- **FR-008**: GARD MUST manage only custom fields and tag slugs declared in the write-back manifest; unrelated NetBox tags MUST be preserved.
- **FR-009**: If the sync phase fails or rolls back, write-back MUST NOT execute.
- **FR-010**: Write-back MUST use a NetBox **write-capable** credential separate from the read-only sync credential (configuration may allow a single token with both scopes in dev only).
- **FR-011**: Each sync run MUST include write-back summary counts (`updated`, `skipped`, `conflict`, `failed`) and MUST emit audit events for write-back start and completion (or failure).
- **FR-011a**: When the sync **pull phase** succeeds, the sync API MUST return **HTTP 200** even if the write-back phase has partial failures; write-back failures MUST be reported in the response body and MUST NOT roll back sync reconciliation results.
- **FR-012**: Write-back MUST support a dry-run or validation mode that checks manifest and NetBox field existence without mutating NetBox (operator tooling).
- **FR-012a**: A documented **dev/lab bootstrap** step MUST create NetBox custom field definitions (and tag objects if not present) from the write-back manifest; production deployments MUST rely on operator-provisioned fields — GARD MUST NOT auto-provision custom fields in production.
- **FR-013**: Production or non-localhost NetBox targets MUST require explicit operator confirmation for write-back (same safety posture as F9 bootstrap).

### Key Entities

- **Write-back manifest** — maps GARD lifecycle attributes to NetBox custom field names and tag slugs; versioned alongside catalog.
- **Write-back report** — per sync run: per-device status (`updated`, `skipped`, `conflict`, `failed`), summary counts, correlation id.
- **Device** (existing) — source of lifecycle state, evaluation summaries, `netbox_device_id`; not mutated by write-back except optional `netbox_last_writeback_at` timestamp.
- **NetBoxSyncRun** (extended conceptually) — sync run aggregates both pull reconciliation counts and write-back counts.

### Lifecycle attributes published (initial set)

The manifest MUST support at minimum these GARD-sourced concepts (exact NetBox field names are manifest-defined):

| GARD concept | Published as |
|--------------|--------------|
| Lifecycle state | Custom field |
| Compliance / drift summary | Custom field |
| Readiness summary | Custom field |
| Target firmware (catalog) | Custom field |
| Last compliance evaluation time | Custom field |
| Last readiness evaluation time | Custom field |
| Drift posture (e.g., outside target) | Tag slug(s) |
| Readiness posture (e.g., blocked, ready for uplift) | Tag slug(s) |
| GARD-managed marker | Tag slug (indicates device is under GARD lifecycle governance) |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one successful sync on a lab estate of at least two NetBox-linked devices with evaluations, **100%** of linked devices show populated GARD custom fields and expected tags in NetBox within the same operator action (no separate write-back command required).
- **SC-002**: A second sync with unchanged evaluations completes write-back with **zero failed devices** and **no duplicate tags** on any NetBox device.
- **SC-003**: When an operator manually changes a GARD-managed custom field in NetBox, the next sync reports that device as **conflict** in the write-back section **100%** of the time (no silent overwrite in default mode).
- **SC-004**: When sync fails during the NetBox pull phase, **zero** NetBox custom fields or tags are modified by GARD in that attempt.
- **SC-005**: Operations reviewers can trace each write-back batch to audit events and summary evidence using a single correlation identifier per sync run.

## Assumptions

- F7 read sync and F9 device-type bootstrap are available; linked devices reference valid NetBox DCIM records.
- NetBox custom fields required by the manifest are **provisioned by operators in production**. In dev/lab, a documented bootstrap step creates fields from the manifest (mirroring F9 device-type bootstrap); F10 write-back does not auto-provision fields outside that dev path.
- GARD compliance and readiness evaluations may already exist before sync; write-back reads **current stored** GARD derived state at post-sync time and **does not** trigger compliance or readiness evaluation as part of sync (operators run evaluate separately when fresh NetBox mirrors are needed).
- Initial manifest covers all vendors/models generically — mappings are device-agnostic and keyed off GARD lifecycle fields, not `model_raw`.
- Post-sync is the **only automatic trigger** in F10; standalone “write-back only” retry may be added as operator tooling but is not required for MVP.
- Operators who need fresh lifecycle values in NetBox SHOULD run compliance/readiness evaluate **before** sync; write-back will then publish those results.
- NetBox v2 API tokens (Bearer format) are used for write operations, consistent with F9 dev stack conventions.

## Dependencies

- **F7** — NetBox read sync, `netbox_device_id`, sync run audit/evidence.
- **F9** — Credible device types in NetBox (prerequisite for operator trust, not a runtime dependency of each write-back call).
- **F3/F4** — Compliance and readiness summaries as write-back sources (devices without evaluations use unknown sentinels).
- **New ADR (planned)** — Supersedes ADR-0017 write-back deferral; defines conflict policy, field ownership, and post-sync coupling.

## Out of scope (F10)

- NetBox device or device-type creation (F9 bootstrap remains the path).
- Pulling observed firmware or lifecycle state **from** NetBox into GARD.
- Diode gRPC ingestion, Assurance rule authoring, or Discovery automation.
- Continuous/real-time push — write-back is tied to sync runs, not evaluation webhooks.
- Bulk import of NetBox custom field definitions in production (operators provision fields; dev bootstrap script handles lab).
