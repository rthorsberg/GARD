# Feature Specification: F3 — Compliance & Drift Evaluation

**Feature Branch**: `003-compliance-drift-evaluation`
**Created**: 2026-05-30
**Status**: Draft
**Input**: User description: "F3 Compliance & Drift Evaluation: ComplianceEvaluation controller, drift taxonomy (target/catalog/package/rule/evidence/discovery/exception drift), explainable response envelope (state/summary/facts/reasons/recommended_actions/confidence), transitions target_defined to compliant/outside_target, MCP tools for compliance reporting. Depends on F1+F2."

## Why this feature exists

F1 told GARD what devices it knows about. F2 told GARD what each device
*should* run, and answered the per-device question "is this one device
on target?". Neither feature lets an operator answer the questions a
network manager actually asks at the start of a Monday:

- "Across my whole estate today, where is the drift, and *what kind* of
  drift is it?"
- "Which devices are non-compliant because the *device* is wrong vs.
  because *the catalog itself* is incomplete?"
- "When I look at one device's verdict, **why** did GARD reach it, and
  **what should I do next**?"

F3 makes those questions answerable. It is the first feature where the
**explainable response envelope** — promised by Constitution Principle V
("Evidence, Audit & Explainability") and scaffolded in F2 as an empty
`recommended_actions: []` — actually carries weight.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Estate-wide drift dashboard (Priority: P1)

A lifecycle manager opens GARD on Monday morning and needs a single
view that summarises drift across the entire estate, decomposed by
**drift type** rather than a flat "X% non-compliant" number. They want
to see, for example: "147 devices have `target_drift` (wrong version),
23 have `catalog_drift` (no target defined for their model), 4 have
`evidence_drift` (last validated > 90 days ago)" — so they can route
work to the right team (the catalog owner, the field team, the audit
team) instead of one undifferentiated triage queue.

**Why this priority**: Without this view, GARD is per-device only. An
operator with 5,000 devices cannot use a per-device endpoint to plan
their day. This is the headline operator value of F3.

**Independent Test**: Seed the F1+F2 demo state (5 devices, 2
targets), call `GET /api/v1/compliance/summary`, assert the response
contains one count per drift type, that the counts sum to total
devices in a firmware-derived lifecycle state, and that drilling into
each drift type via the listing endpoint returns exactly those devices.

**Acceptance Scenarios**:

1. **Given** the F1+F2 demo state, **When** the operator calls
   `GET /api/v1/compliance/summary`, **Then** the response returns a
   per-drift-type count for every drift kind defined in the taxonomy
   (zero allowed) plus a `compliant_count` and a `total_evaluated`.
2. **Given** the summary shows `catalog_drift: 1` (Nokia SR-OS has no
   target), **When** the operator calls
   `GET /api/v1/compliance/devices?drift_type=catalog_drift`, **Then**
   exactly the Nokia device is returned with its full envelope.
3. **Given** a target is added to the catalog covering Nokia SR-OS
   (via a YAML edit + reload), **When** the operator calls the summary
   again, **Then** `catalog_drift` decrements by 1 and `target_drift`
   or `compliant_count` increments by 1 accordingly — without any
   per-device write request.

---

### User Story 2 — Explainable per-device verdict (Priority: P1)

A field engineer is paged about `r1.oslo`. They open its compliance
verdict and need to see: what state the device is in, why GARD reached
that state (with citations to the exact target row, observation, and
catalog file), and a concrete list of recommended next actions — not a
generic "non-compliant, fix it" message. The verdict must be reachable
in one HTTP call (no client-side joining) and must be safe to forward
to an LLM or runbook without leaking implementation details.

**Why this priority**: Constitution V is non-negotiable. F2 shipped
the envelope shape but left `recommended_actions: []`. F3 makes the
envelope deliver on the constitutional promise. P1 because every
downstream tool (MCP, future UI, runbook generators) assumes this
endpoint returns a full envelope.

**Independent Test**: Pick the seeded `r1.oslo` device (Cisco IOS XR
7.5.2 with target 7.8.1). Call
`GET /api/v1/devices/{r1.oslo.id}/compliance`. Assert the response is
a `ComplianceEnvelope` with: `state="outside_target"`, exactly one
classified `drift_type="target_drift"`, `reasons[]` citing the target
id, the observation id, and the catalog file relpath, and
`recommended_actions[]` containing at least one machine-readable
action of kind `upgrade_path_query` with the right `from_version` /
`to_version`.

**Acceptance Scenarios**:

1. **Given** `r1.oslo` is on 7.5.2 with target 7.8.1, **When** GET
   `/api/v1/devices/r1.oslo.id/compliance`, **Then** `state =
   "outside_target"`, `drift_type = "target_drift"`, `reasons[]`
   includes one `kind="version_mismatch"` citing target id, and
   `recommended_actions[]` includes one
   `{kind: "upgrade_path_query", platform_family: "iosxr",
   from_version: "7.5.2", to_version: "7.8.1"}`.
2. **Given** `r3.oslo` is Nokia SR-OS with no target match, **When**
   the same GET, **Then** `state = "classified"`, `drift_type =
   "catalog_drift"`, `reasons[]` includes one
   `kind="no_target_matched"`, and `recommended_actions[]` includes
   `{kind: "define_target", platform_family: "sros",
   vendor_normalized: "nokia"}`.
3. **Given** the device's most recent observation is older than the
   configured staleness threshold, **When** the same GET, **Then** the
   envelope adds `drift_type = "discovery_drift"` as a secondary
   classification and a reason of kind `stale_observation` with the
   observation age in days.
4. **Given** the request is served, **Then** the envelope's
   `correlation_id` matches the response header `X-Correlation-Id`,
   and a single `compliance.evaluated` audit row exists with that
   correlation id, the device id, and the classified drift type(s).

---

### User Story 3 — MCP-callable compliance reporting (Priority: P2)

An AI agent connected via MCP needs to answer operator questions like
"how many devices in the Oslo region are outside their target?" or
"list every device blocked by catalog drift". The agent must reach
the same audited, RBAC-gated answers as the REST surface, with no raw
SQL access, and the response shape must be byte-identical (modulo the
correlation id) to the REST equivalent so prompts can be authored
against one schema.

**Why this priority**: P2 because the REST surface in US1 already
delivers the operator value; MCP tools are a parallel transport. They
also have a hard upstream dependency: the MCP server itself is
deferred to follow-up feature `008-mcp-server` (per ADR-0013). F3
*defines* the tool contracts so they can be ported when the transport
lands, but does not stand the server up.

**Independent Test**: Each tool is defined as a Pydantic input/output
pair plus a thin delegate to the existing controller. Contract tests
lock the JSON schemas. When the MCP transport feature ships, the
tools register without per-feature changes.

**Acceptance Scenarios**:

1. **Given** the tool contracts in `contracts/mcp-tools.yaml`,
   **When** a contract test parses each, **Then** every tool has a
   non-empty `input_schema`, `output_schema`, and a documented `auth`
   permission matching a `Permission` enum value.
2. **Given** `count_devices_outside_target` is invoked with no
   filters, **When** the underlying controller is called, **Then** it
   returns the same integer the REST `/api/v1/compliance/summary`
   would return for `outside_target_count`.
3. **Given** `list_devices_outside_target(region="oslo")` is invoked,
   **Then** the result is a list whose every item also appears in
   `GET /api/v1/compliance/devices?state=outside_target&region=oslo`,
   in the same order, with the same field set.

---

### Edge Cases

- **Empty estate**: zero devices in any firmware-derived state. The
  summary must return zero for every drift type, `compliant_count =
  0`, `total_evaluated = 0`. No error.
- **Empty catalog**: zero firmware targets loaded. Every device that
  has been classified by F1 becomes `catalog_drift`; the summary
  reflects that without crashing or producing a 500.
- **Mid-reload race**: a `firmware_catalog.reload()` runs while a
  `GET /compliance/devices` is mid-flight. The in-flight request must
  see a consistent snapshot — either fully pre-reload or fully
  post-reload, never a mix of one device evaluated against the old
  target set and the next device against the new set.
- **Conflicting drift signals**: a device is both `outside_target`
  (wrong version) *and* its last observation is stale. Both drift
  types must surface, with `target_drift` as primary and
  `discovery_drift` as secondary, *not* one overriding the other.
- **Observation count zero**: device exists, classified, target
  matched, but no `DeviceObservation` rows exist yet. State is
  `target_defined`, drift type is `discovery_drift` (kind
  `missing_observation`), and `recommended_actions[]` includes
  `{kind: "trigger_discovery"}`.
- **Unknown lifecycle state**: a device persisted in `unknown` per
  F2 (ADR-0012) — the summary counts it under a dedicated `unknown`
  bucket, not collapsed into any drift type. Constitution III: never
  coerce missing data.
- **Soft-deleted target between evaluation and report**: a target was
  matched against a device, then removed via a reload. The device's
  current evaluation must reclassify to `catalog_drift` on next
  evaluation; the old `compliant` evidence row is not deleted (audit
  trail), but the live envelope reflects the new reality.
- **High-cardinality summary**: 50,000 devices across 200 targets.
  The summary endpoint must return in under 1 second; it MUST NOT
  evaluate per-device on the hot path — it MUST read from a
  materialised per-device classification row.
- **Stale observation threshold not configured**: the
  `discovery_drift` rule degrades gracefully — devices with old
  observations are not flagged for staleness, but no other drift type
  is suppressed. The summary surfaces a single info-level reason
  saying staleness detection is disabled.

## Requirements *(mandatory)*

### Functional Requirements

**Drift taxonomy & classification**

- **FR-001**: System MUST implement the seven drift types enumerated
  in the seed lifecycle spec: `target_drift`, `catalog_drift`,
  `package_drift`, `rule_drift`, `evidence_drift`, `discovery_drift`,
  `exception_drift`. Each MUST be classifiable in isolation from the
  others.
- **FR-002**: System MUST classify every device that is in a
  firmware-derived lifecycle state (`target_defined`, `compliant`,
  `outside_target`, `unknown`) into zero or more drift types. A device
  may carry multiple drift classifications (e.g.,
  `target_drift + discovery_drift`); the envelope MUST surface them
  in a stable order with one as primary.
- **FR-003**: System MUST persist the classification result per
  device as a `ComplianceEvaluation` row, including the primary drift
  type, all secondary drift types, the resolved target id (if any),
  the observed version (if any), the evaluation timestamp, and the
  correlation id of the originating request.
- **FR-004**: System MUST treat `ComplianceEvaluation` as
  append-only at the row level — re-evaluations create new rows, they
  never UPDATE prior rows. The live envelope reads the latest row per
  device.
- **FR-005**: System MUST emit one `compliance.evaluated` audit row
  per evaluation pass, carrying device id, classified drift types,
  and the correlation id of the request that caused the evaluation.

**Explainable response envelope**

- **FR-006**: System MUST extend F2's `FirmwareComplianceEnvelope`
  shape (or compose alongside it) to include a typed `drift_type`
  field and a non-empty `recommended_actions[]` for every
  non-compliant state.
- **FR-007**: `reasons[]` MUST cite, by stable identifier, every
  artefact contributing to the verdict: the target id (when one
  matched), the observation id (when one was considered), the catalog
  file relpath (when classification depended on what is or isn't in
  the catalog), and the policy decision (when staleness or other
  threshold was the deciding factor).
- **FR-008**: `recommended_actions[]` MUST be a list of typed,
  machine-readable action objects — never free-form prose. v1 action
  kinds: `upgrade_path_query`, `define_target`,
  `trigger_discovery`, `request_observation_refresh`,
  `escalate_to_catalog_owner`, `acknowledge_exception`.
- **FR-009**: Every envelope MUST set `confidence` from F1's
  confidence ladder when an observation contributed, and to `1.0`
  when the verdict is purely catalog-derived (e.g.,
  `catalog_drift` from no matching target). The mapping rule MUST
  be the same as F1/F2 — F3 does not introduce a new confidence
  scale.
- **FR-010**: Envelope serialisation MUST be deterministic given
  the same inputs: `reasons[]` and `recommended_actions[]` MUST
  sort by `kind` then `ref` so consecutive calls produce
  byte-identical responses (modulo `correlation_id` and `as_of`).

**Estate-wide summary & listing**

- **FR-011**: System MUST expose
  `GET /api/v1/compliance/summary` returning per-drift-type counts,
  `compliant_count`, `unknown_count`, and `total_evaluated`. Filters:
  `region`, `site`, `platform_family`, `vendor_normalized` — each
  optional, each composable.
- **FR-012**: System MUST expose
  `GET /api/v1/compliance/devices` returning a paginated list of
  device-with-envelope rows, filterable by `drift_type`, `state`,
  `region`, `site`, `platform_family`, `vendor_normalized`. The page
  shape MUST match F1's listing convention (`items` /
  `total_returned` / `next_page_token`).
- **FR-013**: Summary and listing endpoints MUST serve from the
  persisted `ComplianceEvaluation` rows — they MUST NOT trigger
  per-device evaluation on the read path. Stale evaluations are
  refreshed by the F2 bounded-reeval pipeline and by an explicit
  `POST /api/v1/compliance/evaluate` (US1 admin surface).
- **FR-014**: System MUST expose `POST /api/v1/compliance/evaluate`
  to trigger evaluation for an explicit device set (`{device_ids:
  [...]}` or `{scope_selector: {...}}`). The endpoint MUST be
  bounded — refuse a request that resolves to more than a configured
  cap (default 5,000 devices) with `413 EVALUATION_TOO_LARGE`.

**Drift detection rules**

- **FR-015**: `target_drift` MUST be classified when the device's
  resolved target's `target_version` differs from the latest
  `observed_firmware` in `DeviceObservation` — i.e., the same logic
  F2's compliance controller uses, lifted into the F3 taxonomy.
- **FR-016**: `catalog_drift` MUST be classified when the device is
  in lifecycle state `classified` and no `FirmwareTarget` row's
  `scope_selector` matches the device's facts.
- **FR-017**: `package_drift` MUST be classified when the device's
  resolved target's `target_version` does not have a corresponding
  `FirmwarePackage` row (regardless of `blob_present`), OR when one
  exists but `blob_present = false`.
- **FR-018**: `rule_drift` MUST be classified when the device has a
  matched target and an observed version different from the target
  version, AND no `FirmwareUpgradePath` chain exists from the
  observed version to the target version for that `platform_family`.
- **FR-019**: `discovery_drift` MUST be classified when the device's
  latest `DeviceObservation` is older than the configured staleness
  threshold (default 30 days), OR when the device has zero
  observations.
- **FR-020**: `evidence_drift` MUST be classified when the device's
  current state is `compliant` but no `LifecycleEvidence` row of type
  `re_evaluation` exists within the configured evidence-freshness
  window (default 90 days). v1 does not yet have post-uplift
  validation evidence so this rule is intentionally narrow.
- **FR-021**: `exception_drift` MUST be classified when an
  `Exception` entity references the device AND its `expires_at` has
  passed OR it has no approver recorded. `Exception` is an F5
  entity; in F3 the rule is wired but always evaluates to "no
  exception found" until F5 lands — FR-021 is a forward seam, not a
  v1 deliverable.

**Configuration & RBAC**

- **FR-022**: Staleness thresholds for `discovery_drift` and
  `evidence_drift` MUST be configurable via environment variables
  with documented defaults; changes MUST NOT require a rebuild.
- **FR-023**: All read endpoints MUST require permission
  `READ_COMPLIANCE`. The trigger endpoint
  `POST /compliance/evaluate` MUST require `RUN_COMPLIANCE_EVAL`.
  Both permissions MUST be added to the RBAC matrix and assigned
  to existing roles consistently with F1/F2 conventions.
- **FR-024**: Every endpoint MUST emit one audit row per request:
  `compliance.read` for read paths (with the resolved filter set in
  `after_state`) and `compliance.evaluation_triggered` for the
  trigger path (with the resolved device-id set capped at 100 ids
  echoed back; counts always exact).

**MCP tool contracts (port lands with feature 008)**

- **FR-025**: System MUST publish input/output JSON schemas for
  four MCP tools in `contracts/mcp-tools.yaml`:
  `count_devices_outside_target`,
  `list_devices_outside_target`,
  `get_compliance_summary`,
  `get_unknown_lifecycle_items`.
  Each schema MUST declare its required `auth` permission.
- **FR-026**: F3 MUST NOT register or expose the tools at runtime
  (the MCP transport is deferred per ADR-0013). The tool
  *implementations* live as thin Python delegates over the F3
  controllers and ship with unit tests asserting they return the
  same data as their REST equivalents.

### Key Entities

- **ComplianceEvaluation**: append-only row per device-per-evaluation.
  Stores `device_id`, `primary_drift_type`, `secondary_drift_types[]`,
  `compliance_state` (mirrors F2's `FirmwareComplianceState`),
  `target_ref`, `target_version`, `observed_version`, `evaluated_at`,
  `correlation_id`, `confidence`, and `reasons[]` JSON. The latest
  row per device is the live verdict. Earlier rows are the
  classification audit trail.
- **DriftType** (enum): the seven types in FR-001, plus an internal
  `none` sentinel used in counters for `compliant` devices (never
  surfaces in API responses as a `drift_type` field — the envelope
  uses `null` for compliant devices).
- **RecommendedAction**: typed object with `kind`, `ref` (when the
  action targets a specific catalog row), and `params` (typed dict
  per kind). Never free-form prose.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A lifecycle manager opens GARD and sees the
  drift-by-type breakdown for the entire estate in under 1 second at
  p95, against a synthetic 5,000-device dataset with 200 targets.
- **SC-002**: For any non-compliant device, the operator can answer
  "why is this device non-compliant and what should I do" in a
  single HTTP call — no client-side joining of multiple endpoints.
- **SC-003**: 100% of `compliance.evaluated` audit rows carry the
  correlation id of the originating request and the classified drift
  type(s), measured by sampling 100 random rows after a synthetic
  load test.
- **SC-004**: When a firmware target is added or removed via the F2
  reload pipeline, the drift summary reflects the change within 60
  seconds of the reload's completion, without an explicit operator
  re-evaluation call.
- **SC-005**: Re-evaluating the same device against unchanged inputs
  produces an envelope that is byte-identical to the previous
  evaluation (excluding `correlation_id`, `as_of`, and the
  `ComplianceEvaluation.id`). This is the determinism guarantee that
  makes envelope diffs meaningful in audit reviews.
- **SC-006**: A device classified into multiple drift types (e.g.,
  `target_drift + discovery_drift`) surfaces both types in the
  envelope with the same priority ordering on every call. No
  randomness in primary vs secondary selection.
- **SC-007**: 100% of `recommended_actions[]` entries in any envelope
  are typed objects with a `kind` from the v1 enum; zero free-form
  string actions are emitted, verified by a contract test that
  parses every envelope shape returned by integration tests.
- **SC-008**: The estate-wide summary endpoint never triggers a
  per-device firmware re-evaluation. Verified by an integration test
  that calls the summary 100 times and asserts zero new
  `firmware_target.compliance_evaluated` rows land in the audit table.

## Assumptions

- **F2 merges before F3 implementation begins.** F3's `ComplianceEvaluation`
  controller composes over F2's `FirmwareComplianceEnvelope` and
  F2's compliance controller. The F3 branch will rebase onto `main`
  once F2's PR #2 is merged.
- **The MCP transport remains deferred to feature 008.** F3 ships
  tool *contracts* and pure Python delegates but does not start a
  server. This is consistent with ADR-0013.
- **No new lifecycle states are introduced.** F2 already added
  `unknown`. F3 uses the existing state set verbatim.
- **No write-back to NetBox.** F3 is read-only on infrastructure
  identity; it only writes its own `ComplianceEvaluation`,
  `LifecycleEvidence`, and `AuditEvent` rows.
- **`Exception` entity is a forward seam.** FR-021 references an
  entity F5 will introduce. F3 wires the rule but the rule's
  predicate always returns "no exception" until F5 lands.
- **CSV schema does not change.** F2 already bumped it to 1.1.0; F3
  consumes the existing facts.
- **Drift type ordering for the "primary" classification follows a
  fixed precedence**: `catalog_drift` > `rule_drift` > `package_drift`
  > `target_drift` > `discovery_drift` > `evidence_drift` >
  `exception_drift`. This is a v1 default chosen so the most
  upstream-blocking drift (catalog missing entirely) takes priority
  over a downstream symptom (wrong version). The precedence will be
  documented in an ADR during `/speckit-plan`.
- **`POST /compliance/evaluate` is admin-grade.** It is for operator
  override / debugging; the normal evaluation path is the bounded
  re-eval pipeline F2 already wired into the loader. F3 does not
  introduce a separate worker pool.
- **The summary endpoint reads from the latest `ComplianceEvaluation`
  row per device.** A small SQL window function plus an index on
  `(device_id, evaluated_at DESC)` covers SC-001's p95 budget without
  a separate materialised view.

## Dependencies

- **Upstream (must be merged or stable on `main` before F3 implements)**:
  - F1 — `001-device-import-normalize` (merged to `main`)
  - F2 — `002-firmware-catalog` (PR #2 ready; expected merge before F3
    leaves design phase)

- **Downstream (forward seams, not blockers for F3 shipping)**:
  - F4 readiness — will consume `ComplianceEvaluation` rows to decide
    `ready_for_uplift` vs `blocked`. F3 does not anticipate F4's
    consumer needs beyond persisting the `compliance_state` field.
  - F5 uplift planning — owns the `Exception` entity referenced by
    FR-021.
  - F008 MCP server — picks up the tool contracts published by F3.

## Out of scope for F3 (explicit deferrals)

- **Risk score / risk drift.** Risk scoring is F7's domain (seed
  `07-risk-vulnerability.md`). F3 does not compute risk; an operator
  using the summary endpoint to plan work needs counts, not scores.
- **Live MCP server.** Tool contracts only; transport deferred to F008.
- **Real-time push of summary changes (websockets / SSE).** Summary is
  pull-only in v1.
- **`Exception` entity persistence & approval workflow.** F5.
- **Post-uplift validation evidence emission.** The `evidence_drift`
  rule reads existing evidence rows; emitting validation evidence is
  F6 / uplift execution territory.
- **UI dashboard.** v1 is API + MCP per the constitution.
