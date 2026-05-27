# Feature Specification: Device Import & Normalize

**Feature Branch**: `001-device-import-normalize`
**Created**: 2026-05-27
**Status**: Draft
**Input**: User description: "Ingest device inventory via CSV and normalize raw vendor/model/platform to canonical lifecycle entities; lay platform foundation for audit, evidence, RBAC, REST and MCP"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lifecycle Manager imports a fresh device inventory from CSV (Priority: P1)

A network lifecycle manager exports the current device inventory from the
discovery / spreadsheet system the CSP currently uses and uploads it to
GARD as a CSV. GARD parses every row, records the raw observation, attempts
to normalize each row to a canonical vendor / model / platform, and returns
a per-row outcome so the lifecycle manager can immediately see what was
accepted, what needs review, and what was rejected.

**Why this priority**: Without ingest, GARD has no data to govern. Every
other lifecycle capability — compliance, readiness, planning, MCP queries
— requires devices to exist as canonical records. This is the foundational
slice that makes GARD a working system.

**Independent Test**: Given a CSV with 100 rows mixing valid Cisco
ISR1121 entries, malformed rows, and unknown-vendor rows, the lifecycle
manager can upload the file, receive a per-row outcome report, and then
list canonical `Device` records via API or MCP. Delivered value: the
estate is visible to GARD for the first time.

**Acceptance Scenarios**:

1. **Given** a well-formed CSV of 100 rows with known vendor/model/platform
   values, **When** the lifecycle manager uploads it through the import
   endpoint, **Then** GARD records one `DeviceObservation` per row, creates
   or updates one canonical `Device` per row, returns an import summary
   stating 100 accepted / 0 rejected / 0 needs-review, and the lifecycle
   manager can list every device via the device listing endpoint.
2. **Given** a CSV containing 5 rows with missing required columns and 3
   rows with vendor values that have no normalization rule, **When**
   uploaded, **Then** GARD rejects the 5 malformed rows with a per-row
   reason, accepts the 3 unknown-vendor rows but marks them with
   `confidence: manual_review_required`, records `DeviceObservation`s for
   all 8 rows, and returns a downloadable error/exception report.
3. **Given** a previous CSV import for the same devices exists, **When** a
   second CSV is imported with updated firmware values for the same
   hostnames / serials, **Then** GARD creates new `DeviceObservation`
   records (does not overwrite prior observations) and updates each
   canonical `Device`'s lifecycle state to reflect the latest observation.

---

### User Story 2 - Lifecycle Manager / Engineer reviews and corrects normalization outcomes (Priority: P2)

After an import, the lifecycle manager opens the list of rows flagged
`manual_review_required` (unknown vendor, ambiguous model, or low-confidence
match) and either (a) adds a normalization rule that will resolve them, or
(b) manually maps individual rows to a canonical vendor / model /
platform. Re-running the import against the updated rules clears the
manual-review backlog without re-uploading the file.

**Why this priority**: Normalization is the most common source of "unknown"
records in CSP estates (legacy vendors, renamed models, OEM variants).
Without a review-and-correct loop, "unknown" piles up and Principle III
of the constitution (no silent defaults, no hidden rows) is meaningless.

**Independent Test**: Given 10 rows from a prior import flagged
`manual_review_required`, an engineer can add a normalization rule and
re-evaluate the affected observations, after which the rows are
re-classified to a canonical platform without re-uploading the CSV.

**Acceptance Scenarios**:

1. **Given** an import produced 12 observations with
   `confidence: manual_review_required`, **When** the lifecycle manager
   lists pending-review observations, **Then** GARD returns all 12 with
   the original raw values, the rule (if any) that matched partially, and
   the reason for the manual-review verdict.
2. **Given** a new normalization rule mapping `vendor_raw="ZyXEL"` to
   `vendor_normalized="Zyxel"`, **When** the rule is added and the lifecycle
   manager triggers re-evaluation, **Then** every previously
   manual-review observation matching the new rule moves to
   `confidence: high` or `exact`, the corresponding `Device` records are
   updated, and an audit event records the re-evaluation.
3. **Given** an observation that cannot be normalized by any rule, **When**
   an engineer manually maps it to a canonical vendor / model / platform,
   **Then** GARD records the manual mapping, attaches an audit event with
   actor and reason, and emits a `LifecycleEvidence` record for the manual
   classification.

---

### User Story 3 - AI agent queries the canonical device estate via MCP (Priority: P2)

An approved AI agent (chatbot or IDE copilot) calls the MCP server to
answer "How many Cisco ISR1121 devices does GARD currently know about, and
how many are unclassified?" The agent receives a structured response within
the same audit and RBAC pipeline as a human REST caller — no raw SQL, no
shell, no unbounded queries.

**Why this priority**: ADR-0003 commits GARD to MCP-native from v1. F1
needs to deliver the first usable MCP tools so the architecture is proven
end-to-end (auth → RBAC → curated tool → controller → response), not just
"planned for later". This forces the MCP foundation to land alongside the
REST foundation, not after it.

**Independent Test**: Given a populated `Device` table after an import, an
MCP client with read-only credentials can call `list_devices` and
`get_device_lifecycle_status` and receive bounded, schema-validated
responses, while every call is recorded in the audit log with a
correlation id matching the response.

**Acceptance Scenarios**:

1. **Given** 184 imported Cisco ISR1121 records and the MCP server is
   running, **When** an approved MCP client calls `list_devices` with
   filter `{vendor: "Cisco", model: "ISR1121"}`, **Then** GARD returns a
   paginated, schema-validated response listing the matching devices and
   their lifecycle states, and an `AuditEvent` is recorded with the
   client identity, tool name, and a correlation id present in both
   audit log and structured response headers.
2. **Given** an MCP client without read permission for devices, **When**
   it calls `list_devices`, **Then** GARD returns a permission-denied
   response, records an `AuditEvent` with `result: denied`, and does not
   leak record counts or schemas.
3. **Given** a request that would return more than the pagination limit,
   **When** the MCP client calls `list_devices`, **Then** GARD returns
   the first page with a `next_page_token`, never an unbounded response.

---

### Edge Cases

- **Duplicate rows in a single CSV**: rows with identical hostname +
  serial are de-duplicated to one canonical `Device`, but each row still
  produces its own `DeviceObservation` for traceability.
- **Conflicting rows for the same device**: two rows in the same CSV with
  the same hostname/serial but different firmware values — both
  observations are recorded; the canonical `Device`'s lifecycle state
  reflects the most-recently-observed value per the rules, and a warning
  is included in the import summary.
- **Re-import of the same file**: detected via content hash; GARD refuses
  the duplicate import by default and offers an explicit
  "import anyway" path that is separately audited.
- **CSV character encoding**: UTF-8 is required; non-UTF-8 input is
  rejected with an explicit encoding error rather than silently
  mis-decoded.
- **Extremely large CSV** (e.g., 250k rows): the import endpoint accepts
  the upload but processes asynchronously, returning a job id; status and
  results are retrievable via a polling endpoint.
- **CSV with extra / unknown columns**: extra columns are preserved in the
  raw observation payload but ignored for normalization; the import does
  not fail.
- **Hostname collision across sites**: two devices with the same hostname
  in different sites are treated as distinct canonical `Device` records
  (uniqueness is on hostname + site, or on serial when present).
- **Normalization rule conflict**: when two rules match the same raw
  value with different outputs, GARD applies the highest-specificity /
  highest-priority rule deterministically and surfaces the conflict in
  the rule-review report. It MUST NOT silently pick one.
- **Missing serial number**: serial is optional in the canonical model;
  identity falls back to hostname + site. Devices without either are
  rejected with a clear reason.
- **Auth/RBAC failure mid-import**: the request is rejected before any
  rows are written; no partial state is persisted.

## Requirements *(mandatory)*

### Functional Requirements

**Ingest**

- **FR-001**: System MUST provide an authenticated REST endpoint that
  accepts a UTF-8 CSV file containing device inventory rows.
- **FR-002**: System MUST validate every row against a documented CSV
  schema (required columns, allowed types) and reject rows that violate
  the schema with a row-level reason.
- **FR-003**: System MUST persist every accepted row as a
  `DeviceObservation` capturing the raw payload, the observed firmware,
  the observation source, the observation timestamp, and a confidence
  level.
- **FR-004**: System MUST refuse a re-upload of an identical CSV file
  (detected by content hash) by default, while permitting an explicit,
  separately-audited override.
- **FR-005**: System MUST return an import summary including, at minimum,
  total rows / accepted / rejected / manual-review / new-devices /
  updated-devices / duplicate-rows / warnings, and MUST produce a
  per-row error / exception report retrievable for at least 30 days
  after the import.
- **FR-006**: System MUST process imports of up to 10,000 rows
  synchronously and MUST accept larger imports asynchronously, returning
  a job id and exposing job status and final results via a polling
  endpoint.

**Normalize**

- **FR-007**: System MUST normalize raw vendor / model / platform_family
  values to a canonical taxonomy via a versioned, file-backed
  normalization ruleset that is loadable as code (consistent with
  Constitution Principle IV — Lifecycle-as-Code).
- **FR-008**: System MUST record on every `DeviceObservation` a
  `confidence` value from a fixed enumeration (`exact`, `high`, `medium`,
  `low`, `manual_review_required`) determined by the rule that matched.
- **FR-009**: System MUST upsert a canonical `Device` record per
  observed device using a deterministic identity rule
  (serial when present, otherwise hostname + site) and MUST NOT collapse
  two distinct devices into one canonical record.
- **FR-010**: System MUST never silently coerce missing or unmatched
  values into defaults; unmatched rows MUST become
  `confidence: manual_review_required` with the raw values preserved
  verbatim (consistent with Constitution Principle III — Unknown is a
  first-class state).
- **FR-011**: System MUST surface deterministic conflict resolution
  when two normalization rules match the same raw value, and MUST list
  the conflict in a rule-conflict report.
- **FR-012**: Users with the `lifecycle_manager` permission MUST be able
  to list, add, update and disable normalization rules through the API,
  and the same actions MUST be possible by editing the file-backed
  ruleset and reloading.
- **FR-013**: Users with the `lifecycle_manager` permission MUST be able
  to re-evaluate normalization for a filtered set of `DeviceObservation`
  records without re-uploading the source CSV.

**Lifecycle state & explainability**

- **FR-014**: System MUST set each canonical `Device`'s `lifecycle_state`
  to `imported` on first creation and to `classified` once normalization
  produces a non-manual-review confidence.
- **FR-015**: Every classification decision returned by the API or MCP
  MUST include the rule id (or "manual mapping" reference), the matched
  inputs, and a short human-readable reason — the explainable response
  envelope mandated by Constitution Principle V.

**Auth, RBAC, audit, evidence (platform-foundation work carried by F1)**

- **FR-016**: System MUST require authentication on every API and MCP
  request and MUST enforce per-role permissions matching at minimum the
  roles `viewer`, `lifecycle_manager`, `mcp_client`, `system_admin`.
- **FR-017**: System MUST emit an append-only `AuditEvent` for every
  state-mutating action (import accepted, import overridden, rule
  added/changed/disabled, manual mapping created, re-evaluation
  triggered) including actor, action, object reference, before/after
  values, result, and a correlation id.
- **FR-018**: System MUST emit a `LifecycleEvidence` record for each
  import (with before/after device counts and a checksum of the source
  file) and for each manual classification.
- **FR-019**: System MUST emit structured logs for every request
  carrying the same `correlation_id` used in the audit log and the
  response envelope.
- **FR-020**: System MUST refuse requests carrying credentials lacking
  the relevant permission and MUST record the denial in the audit log
  with `result: denied`.

**MCP**

- **FR-021**: System MUST expose an MCP server with at minimum the
  read-only tools `list_devices` and `get_device_lifecycle_status`,
  each with an input schema, a bounded output schema, and pagination
  for list outputs.
- **FR-022**: MCP tool calls MUST flow through the same authentication,
  RBAC, and audit pipeline as REST endpoints, with no shortcut path.
- **FR-023**: MCP MUST NOT expose raw SQL, shell, file-system, or
  unrestricted device-management access at any time
  (Constitution Principle VI).

### Key Entities

- **Device**: The canonical, deduplicated record for a network device
  GARD is governing. Carries normalized vendor / model / platform_family,
  identity attributes (hostname, site, serial), and a `lifecycle_state`.
  The single record that the rest of GARD (compliance, readiness,
  planning) operates on.
- **DeviceObservation**: A time-bound observation of a device's actual
  state, sourced from a CSV import (in F1) or another source later.
  Immutable once written; carries raw payload, observed firmware,
  observation source, observation timestamp, and the confidence verdict
  from normalization.
- **NormalizationRule**: A pattern + canonical mapping that translates
  raw vendor / model / platform values to canonical ones. Versioned,
  loadable from files, editable via API; carries a priority used for
  deterministic conflict resolution.
- **ImportJob**: A record of a CSV import attempt — file hash, size, row
  counts, status (`processing`, `completed`, `failed`), summary, and a
  link to the per-row error / exception report.
- **AuditEvent**: Append-only record of any state-mutating action;
  carries actor, action, object reference, before/after, result, and
  correlation id. Cross-cutting; F1 establishes the pipeline.
- **LifecycleEvidence**: Structured proof of a lifecycle-relevant event
  (in F1: the import event, the manual classification event); carries
  before/after state, actor, checksum, and references.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A lifecycle manager can upload a 10,000-row CSV and receive
  the import summary within 30 seconds of upload completion under nominal
  conditions.
- **SC-002**: After an import of a representative CSP estate sample,
  ≥ 95 % of rows from the targeted reference vendors (Cisco ISR1121 in the
  MVP vertical slice) are classified at `confidence: exact` or `high`
  with zero manual intervention.
- **SC-003**: 100 % of imported rows are represented exactly once as
  either an accepted observation or a per-row rejection with a
  human-readable reason — no rows are silently dropped.
- **SC-004**: 100 % of `manual_review_required` observations are
  discoverable via a dedicated listing endpoint and 100 % become
  re-classifiable through either a new normalization rule or a manual
  mapping, without re-uploading the source CSV.
- **SC-005**: An approved MCP client can answer
  "How many devices of vendor X / model Y does GARD currently know
  about?" in under 2 seconds for an estate of up to 50,000 devices,
  using only curated MCP tools.
- **SC-006**: 100 % of state-mutating requests (import, override,
  rule change, manual mapping, re-evaluation) appear in the audit log
  with a correlation id retrievable from the originating response.
- **SC-007**: 100 % of imports produce a `LifecycleEvidence` record
  with a verifiable source-file checksum.
- **SC-008**: Zero requests are accepted without authentication; zero
  state-mutating requests succeed without the matching permission.

## Assumptions

- **Reference vendor for v1**: Cisco ISR1121 is the primary reference
  device family for normalization rule coverage and acceptance metrics,
  matching the seed material's MCP examples.
- **Discovery source**: device inventory is exported from the CSP's
  existing discovery / inventory system to CSV; native discovery is out
  of scope (deferred to a later feature).
- **NetBox**: NetBox is the eventual source of identity reference
  (ADR-0001), but F1 ingests CSV only; the NetBox read-side integration
  is a separate feature (F7).
- **CSV schema authority**: the CSV column schema is owned by GARD;
  during this feature it is defined once, versioned, and shipped with
  a sample file under `gard-speckit-start/examples/devices.csv`.
- **Async threshold**: the 10,000-row sync/async boundary in FR-006 is
  a reasonable default for CSP estates; the threshold is configurable
  and is itself recorded as a versioned setting.
- **Roles**: the RBAC roles used in F1 are a subset of the security spec
  (`viewer`, `lifecycle_manager`, `mcp_client`, `system_admin`); the
  full role catalogue lands later as more capabilities ship.
- **MCP transport**: the MCP server transport (HTTP vs. stdio) and
  authentication mechanism are settled in the F1 plan; the spec only
  requires that auth and audit apply uniformly.
- **Storage**: audit log and evidence storage choices (database tables
  vs. append-only object storage) are decided in F1's
  `ADR-0009 Audit & evidence storage strategy`; the spec only requires
  append-only semantics and queryability.
- **Idempotent re-imports**: re-import detection is by source-file
  content hash; a future feature may add hostname/serial-level
  idempotency tokens.
- **Performance under contention**: SC-001's 30-second budget assumes a
  single concurrent import; multi-tenant / heavy-concurrency goals are
  out of scope for v1.

## Dependencies

- **None upstream** — F1 is the foundation feature on the GARD roadmap.
- **Downstream consumers**: F2 (firmware catalog) and F3 (compliance
  evaluation) both require `Device` and `DeviceObservation` to exist;
  F7 (NetBox integration) requires the canonical `Device` shape and the
  audit/evidence pipeline.
