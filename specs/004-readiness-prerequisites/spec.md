# Feature Specification: Readiness & Prerequisites

**Feature Branch**: `004-readiness-prerequisites`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F4 — Readiness & Prerequisites: decide which `outside_target` devices are SAFE to uplift; transition `outside_target → ready_for_uplift / blocked` based on the F2 prerequisite catalogue plus reachability of an upgrade chain; emit explainable blocker lists; expose `get_readiness_summary` and `explain_blockers` MCP tools."

## Why this feature exists

After F3, the operator knows **which** devices are off-target and **why** (drift type). F4 answers the next question every uplift planner asks before lifting a finger:

> *Of these N devices that are off-target, which ones are SAFE to upgrade right now, which ones are BLOCKED, and what — precisely — is blocking each one?*

Without F4, every uplift attempt is a roll of the dice: the device might lack RAM, lack disk, lack a licence, lack a hardware revision, or sit on a firmware version with no upgrade path that reaches the target. F4 makes the answer **deterministic and citable**: every blocker references a specific prerequisite rule or upgrade-path absence, with the exact missing input named. F5 (Uplift Planning) then takes this signal as the *only* admissible input to wave construction — `outside_target` is not enough; `ready_for_uplift` is the green-light state.

GARD already has the raw material: F2's `firmware_prerequisite_rules` catalogue + `firmware_upgrade_paths` graph, F3's `compliance_evaluations` table, and the device observation history. F4 stitches them into a single readiness verdict per device, persists it, and re-evaluates exactly the touched devices when the catalogue changes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Estate-wide readiness dashboard (Priority: P1)

A capacity-planning lead opens the operator console at the start of the quarter. She wants one screen that tells her: "Out of our 5,000 off-target devices, how many are actually ready to schedule for uplift this quarter, how many are blocked, and what's the dominant blocker category?" — without joining four endpoints by hand.

**Why this priority**: This is the question every quarterly capacity plan starts with. Without a single estate-wide readiness counter, every planning meeting becomes a manual spreadsheet exercise — defeating the entire automation premise of GARD.

**Independent Test**: Against the seeded 5-device fixture, `GET /api/v1/readiness/summary` returns counters that sum to the F3 `outside_target_count` and break down by `ready_for_uplift_count`, `blocked_count`, and a `top_blocker_categories[]` array. Filtering by `region=oslo` returns counters that match the manual ground truth derived from the per-device endpoint.

**Acceptance Scenarios**:

1. **Given** the estate has 5,000 `outside_target` devices, **When** the planner calls `GET /api/v1/readiness/summary`, **Then** the response includes `ready_for_uplift_count`, `blocked_count`, and `top_blocker_categories[]` (with kind + count) that sum correctly.
2. **Given** a region filter `region=oslo`, **When** the planner calls the summary endpoint, **Then** counters reflect only Oslo devices and `filters_applied.region == "oslo"`.
3. **Given** F2's prerequisite catalogue gains a new `min_ram_mb` rule that newly blocks 200 devices, **When** the catalogue reloads, **Then** the next summary call reflects the updated `blocked_count` without per-device API calls.

---

### User Story 2 - Explainable per-device readiness verdict (Priority: P1)

A field engineer is paged at 02:00 about `r1.oslo` showing up on the morning uplift wave's "blocked" list. He hits one endpoint with the device id and gets: *"This device is BLOCKED because it has 1,024 MB RAM and prerequisite `iosxr-minimum-ram` requires 2,048 MB; the upgrade chain from 7.5.2 → 7.8.1 exists; recommended action is to schedule a hardware refresh."*

**Why this priority**: Without an explainable verdict — every blocker citing a specific rule and missing input — operators end up in the same position as before F3: "the system says no, but I don't know why." Constitution V mandates no opaque verdicts.

**Independent Test**: For each seeded device classified as `outside_target` by F3, `GET /api/v1/devices/{id}/readiness` returns an envelope whose `state` (`ready_for_uplift` | `blocked`), `blockers[]` array (each citing a rule id + missing input), and `recommended_actions[]` match a known per-device truth table.

**Acceptance Scenarios**:

1. **Given** device `r1.oslo` has 1,024 MB RAM and the `iosxr-minimum-ram` rule requires 2,048 MB, **When** the engineer calls `GET /api/v1/devices/{id}/readiness`, **Then** the envelope returns `state=blocked` with one blocker citing the rule id, `predicate_kind=min_ram_mb`, `required=2048`, `observed=1024`, and a `recommended_action` of kind `hardware_refresh`.
2. **Given** device `r2.oslo` meets every required prerequisite AND F2's upgrade-path graph contains a chain to the target version, **When** the engineer calls the per-device endpoint, **Then** the envelope returns `state=ready_for_uplift` with `blockers=[]` and a `recommended_action` of kind `schedule_uplift_wave`.
3. **Given** F2's upgrade-path graph has NO chain from observed_version to target_version on the device's platform, **When** the engineer calls the endpoint, **Then** the envelope returns `state=blocked` with a blocker of `kind=missing_upgrade_path` referencing the platform family.
4. **Given** the per-device call against a `compliant` device, **When** the engineer hits the endpoint, **Then** the response returns 200 with `state=not_applicable` and the envelope's `reasons[]` cites `already_compliant` (F4 has nothing to do).
5. **Given** the per-device call against a `classified` device (no target resolved by F3), **When** the engineer hits the endpoint, **Then** the response returns 200 with `state=not_applicable` and `reasons[]` cites `no_target_resolved`.

---

### User Story 3 - MCP-callable readiness reporting (Priority: P2)

An AI assistant in the operator's IDE asks the GARD MCP server: *"Show me every device blocked by a hardware constraint in the Bergen region so I can draft a hardware-refresh ticket batch."* The assistant uses `explain_blockers` and `get_readiness_summary` to compose its answer — same data, same audit, same RBAC as the REST UI.

**Why this priority**: This is the canonical "AI as a power user" workflow GARD is being designed to enable. P2 only because the MCP transport is still deferred to F008; F4 ships contracts + delegates so F008 can wire them with zero per-tool work.

**Independent Test**: Each MCP tool's delegate returns byte-identical data (modulo correlation_id) to the equivalent REST endpoint for the same filter set.

**Acceptance Scenarios**:

1. **Given** the AI agent calls `get_readiness_summary(region="bergen")` via MCP, **When** the delegate executes, **Then** the response matches `GET /api/v1/readiness/summary?region=bergen` data verbatim.
2. **Given** the AI agent calls `explain_blockers(device_id=…)` via MCP, **When** the delegate executes, **Then** the response is the same `blockers[]` array the REST endpoint returns for that device.
3. **Given** a viewer-role token, **When** the AI agent calls any readiness MCP tool, **Then** the tool resolves (read-only) and emits a `readiness.read` audit row.

---

### Edge Cases

- **No prerequisite rules in the catalogue.** F4 falls back to "upgrade-path-only" readiness: a device is `ready_for_uplift` iff (a) a chain to the target exists AND (b) all *evaluable* observation fields are present. Envelope cites `no_rules_loaded`.
- **A prerequisite rule has `evaluable=false`.** F4 treats it as a soft signal: surfaces a blocker of severity `recommended`, but does not flip the device to `blocked`. The truth table is exhaustively specified in the data model so operators can audit this.
- **Observation is missing the input a rule needs** (e.g., rule wants `ram_mb` but the F1 import skipped the column). F4 emits a blocker of `kind=missing_observation_field`, severity `required`, naming the field. Constitution III: never coerce — never assume zero RAM.
- **Two rules of the same kind apply** (e.g., one platform-wide `min_ram_mb=1024`, one platform+region `min_ram_mb=2048`). F4 takes the **stricter** rule and cites it; the looser is recorded as `runner_up` in the envelope reasons.
- **Upgrade-path chain exists but each edge has a `weight > readiness_weight_cap`** (operator marked the chain as "do not auto-traverse"). F4 returns `state=blocked` with `kind=upgrade_path_too_heavy` referencing the weight cap setting.
- **Device's prior `compliance_evaluation` row is stale** (older than `GARD_READINESS_STALE_DAYS`). F4 refuses to render a verdict from stale F3 input — returns 409 `READINESS_INPUT_STALE` with a structured error pointing the caller at `/compliance/evaluate`.
- **A re-evaluation triggered by F2 reload changes a device's blocker set.** F4 persists a new `ReadinessEvaluation` row only on verdict change (idempotency contract, mirrors F3 R-4).
- **Operator queries readiness for a device whose F3 row says `unknown` lifecycle.** F4 returns 200 with `state=not_applicable` + reason `lifecycle_unknown`; no readiness verdict can be derived without a resolved target.

## Requirements *(mandatory)*

### Functional Requirements

**Readiness taxonomy**

- **FR-001**: System MUST classify every `outside_target` device into exactly one readiness state: `ready_for_uplift`, `blocked`, or `not_applicable`.
- **FR-002**: System MUST surface, for every device in `state=blocked`, a non-empty `blockers[]` list where each blocker cites (a) the rule id when from F2's prerequisite catalogue, (b) the predicate kind, (c) the required value or set, (d) the observed value, and (e) a severity (`required` | `recommended`).
- **FR-003**: System MUST classify a device as `blocked` if AND ONLY IF at least one `required`-severity blocker fires. `recommended`-severity blockers surface in the envelope but do not flip the state.
- **FR-004**: System MUST classify a device as `ready_for_uplift` if AND ONLY IF (a) it is `outside_target` per F3, (b) every required prerequisite rule applying to it evaluates to a pass, (c) an upgrade-path chain from observed_version to target_version exists on the device's platform_family, and (d) all evaluable observation fields needed by the applicable rules are present.
- **FR-005**: System MUST return `state=not_applicable` for devices whose F3 verdict is `compliant`, `classified`, `target_defined`, or `unknown`; this is a successful 200 response with a reason citing why F4 has nothing to do.

**Explainable response envelope**

- **FR-006**: `GET /api/v1/devices/{device_id}/readiness` MUST return the F3 response envelope shape extended with `state`, `blockers[]`, `recommended_actions[]`, `target_version`, `observed_version`, `applicable_rules_count`, `correlation_id`, and `evaluation_id` (foreign key into F4's storage).
- **FR-007**: Every blocker MUST be machine-parseable with a closed enum of `predicate_kind` values that matches F2's `firmware_prerequisite_rules.predicate_kind` plus two new kinds reserved for F4 internally: `missing_upgrade_path` and `missing_observation_field`.
- **FR-008**: Recommended actions MUST be typed with at least the following kinds: `schedule_uplift_wave`, `hardware_refresh`, `license_acquire`, `firmware_intermediate_step`, `import_observation`, `escalate_to_catalog_owner`. Each carries the minimum machine-parseable payload an operator (or AI agent) needs to act.

**Estate-wide summary**

- **FR-009**: `GET /api/v1/readiness/summary` MUST return `ready_for_uplift_count`, `blocked_count`, `not_applicable_count`, `top_blocker_categories[]` (each `{predicate_kind, count}`, sorted by count desc, max 10 entries), `filters_applied`, `as_of`, and `correlation_id`.
- **FR-010**: The summary endpoint MUST accept the same filter set as F3's `/compliance/summary`: `region`, `site`, `platform_family`, `vendor_normalized` — all optional, AND-composed.
- **FR-011**: The summary endpoint MUST be derived from the latest persisted `ReadinessEvaluation` row per device (mirrors F3's DISTINCT-ON pattern); it MUST NOT trigger evaluation on the hot path.

**Bulk listing + trigger**

- **FR-012**: `GET /api/v1/readiness/devices` MUST page through devices in `state=blocked` or `state=ready_for_uplift` with cursor-based pagination (matches F3's keyset cursor).
- **FR-013**: `POST /api/v1/readiness/evaluate` MUST accept either `device_ids[]` or `scope_selector{}` (mutually exclusive, mirrors F3 contract), resolve the set, cap at the same `GARD_COMPLIANCE_EVALUATE_MAX_BATCH` (default 5,000), and refuse larger sets with a 413 `EVALUATION_TOO_LARGE` envelope.
- **FR-014**: The trigger endpoint MUST emit one `readiness.evaluation_triggered` audit row per call plus one `readiness.evaluated` per device whose verdict changed.

**Storage + idempotency**

- **FR-015**: Each successful per-device evaluation that produces a *different* verdict than the latest persisted row MUST insert one new `ReadinessEvaluation` row; re-evaluations against unchanged inputs MUST be silent (no row, no audit) — same idempotency contract as F3 R-4.
- **FR-016**: `ReadinessEvaluation` rows MUST be append-only; pruning (if any) is a v2 concern documented in the migration's docstring.
- **FR-017**: System MUST update the device's `lifecycle_state` to `ready_for_uplift` or `blocked` (or keep it as the F3-set value when readiness is `not_applicable`) atomically with the evaluation row insert, via the same writer session.

**Configuration & RBAC**

- **FR-018**: New permissions MUST be added: `READ_READINESS` (viewer+) and `RUN_READINESS_EVAL` (lifecycle_manager+).
- **FR-019**: Configurable settings MUST include `GARD_READINESS_STALE_DAYS` (default 30; minimum 1) which controls when F4 refuses to derive a verdict from stale F3 compliance input, and `GARD_READINESS_UPGRADE_WEIGHT_CAP` (default 1000; >= 1) which controls when an upgrade chain is rejected for being "too heavy".

**Reload sync**

- **FR-020**: Catalog reloads that touch `firmware_prerequisite_rules` or `firmware_upgrade_paths` MUST trigger bounded re-evaluation for the affected devices, mirroring the F2 → F3 hook that F3 already extended. F4 piggybacks on that same hook; no new scheduler.
- **FR-021**: F3 catalogue-induced compliance changes (e.g. a new target making more devices outside_target) MUST also cascade into F4 evaluation in the same reload pass.

**MCP tool contracts**

- **FR-022**: System MUST publish four read-only MCP tool contracts: `get_readiness_summary`, `list_blocked_devices`, `explain_blockers`, and `get_ready_for_uplift_devices`. Contracts MUST declare input schema, output schema, and required permission.
- **FR-023**: Each MCP tool MUST ship as a Python delegate that returns data byte-parity with the REST equivalent (modulo correlation_id). Transport binding stays deferred to F008 per ADR-0013.

**Determinism**

- **FR-024**: Evaluating the same device against the same catalogue state MUST produce a byte-identical envelope (modulo `correlation_id`, `as_of`, and `evaluation_id`). `blockers[]` and `recommended_actions[]` MUST sort stably on `(severity desc, predicate_kind, rule_id)` and `(kind, JSON payload)` respectively.

### Key Entities *(include if feature involves data)*

- **ReadinessEvaluation**: Append-only row capturing one per-device readiness verdict. Carries `device_id`, `compliance_evaluation_ref` (FK into F3's table — proves which F3 verdict this is built on), `readiness_state`, `blockers[]` (JSONB), `recommended_actions[]` (JSONB), `applicable_rules_count`, `upgrade_path_exists`, `confidence`, `evaluated_at`, `correlation_id`, `actor`.
- **Blocker** (in-envelope and JSONB): `{rule_id?, predicate_kind, severity, required, observed, detail}`. Stable JSON shape so contract tests can lock it.
- **RecommendedAction** (reused from F3 with new kinds added): The four new F4 action kinds extend F3's `RecommendedActionKind` Literal — F3's existing vocabulary stays valid; F4 widens it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A capacity planner viewing the readiness summary for a 5,000-device estate sees a verdict within 1 second p95.
- **SC-002**: For any device classified `blocked`, the engineer can identify the *single most actionable* blocker (highest severity, lowest precedence index) without reading more than the first line of the `blockers[]` array.
- **SC-003**: 100% of `blocked` envelopes cite a specific `rule_id` (when the blocker is from F2's catalogue) or a closed-enum `predicate_kind` (when synthetic) — zero free-form blocker reasons.
- **SC-004**: Re-evaluating an unchanged device set produces zero new `ReadinessEvaluation` rows and zero audit emissions (idempotency contract holds).
- **SC-005**: A catalogue reload that adds N new prerequisite rules triggers at most one re-evaluation per device whose facts match an `applies_to` selector of any new/changed rule; unaffected devices receive no new evaluation row.
- **SC-006**: All four MCP tool delegates return data byte-parity (modulo correlation_id) with the equivalent REST endpoint on a 100-device synthetic fixture.
- **SC-007**: Evaluating the seeded 5-device fixture produces a per-device truth table that matches `quickstart.md` §1 verbatim — including which devices flip to `blocked` (with the precise rule id cited).
- **SC-008**: Operators with a `viewer` role can read all four readiness endpoints; only `lifecycle_manager` or `system_admin` can call the trigger endpoint.

## Assumptions

- **F2's prerequisite catalogue is the single source of truth for prerequisite rules.** F4 does not author rules; it consumes them. The catalogue's existing predicate kinds (`min_ram_mb`, `min_disk_mb`, `min_current_version`, `hardware_revision_in`, `license_present`, `intermediate_version_required`, `not_in_state`, `region_in`, `tagged_with`) cover v1's needs.
- **F2's upgrade-path graph is authoritative for chain existence.** F4 reuses the existing `upgrade_path_graph` cache module — re-implementing the traversal would risk drift between the F2 endpoint's answer and F4's verdict.
- **F3's `compliance_evaluations` is the *only* input** that tells F4 which devices are `outside_target` and what their target_version is. No re-querying F2 directly.
- **F1's `DeviceObservation` is the source of observed inputs** (ram_mb, disk_mb, licenses, hardware_revision, observed_firmware). Missing inputs are treated as missing, never zero.
- **The `not_applicable` state is not a lifecycle_state value** — it is a readiness-only verdict. The device's persisted `lifecycle_state` remains whatever F3 set it to.
- **Hardware-refresh recommendations cite the missing input** (e.g., "needs RAM ≥ 2,048 MB; observed 1,024 MB"), not a specific vendor SKU. SKU mapping is a v2 concern.
- **The `tagged_with` predicate stays deferred** (matches F2's `predicate_deferred` reason in the scope_selector evaluator). F4 surfaces a `recommended`-severity blocker noting deferral; never flips a device to `blocked` on tag input alone.
- **F4's storage is the second derived-state cache in GARD** (after F3's `compliance_evaluations`). Audit + chain-of-custody continue to live in `audit_events` + `lifecycle_evidence`.
- **The constitution III "never coerce" rule extends to readiness**: a missing observation input that a required rule depends on flips the verdict to `blocked`, not "assume pass".
- **No new MCP transport** — F4 ships delegates (matching F3's pattern); the MCP server still ships in F008 (ADR-0013).
- **`exception_drift` from F3 does not influence readiness** in v1 — F5 will handle exception-overridden readiness verdicts. v1 always treats the exception seam as "no exception".

## Dependencies

- **F1** — `DeviceObservation` (ram_mb, disk_mb, licenses, hardware_revision, observed_firmware), `Device`, `LifecycleState` enum.
- **F2** — `FirmwarePrerequisiteRule`, `FirmwareUpgradePath`, `scope_selector.evaluate`, `upgrade_path_graph.UpgradePathGraphCache`.
- **F3** — `ComplianceEvaluation` (the latest row per device is the input to F4), `DriftType`/`primary_drift_type`, the typed `RecommendedAction` vocabulary, the `Permission.READ_COMPLIANCE` + `Permission.RUN_COMPLIANCE_EVAL` RBAC pattern, the bounded `_reevaluate_compliance_post_reload` hook.
- **Constitution V** (audit + explainability) and **Constitution III** (never coerce missing inputs).
- **ADR-0011** (catalog-as-code mutation discipline) and **ADR-0013** (MCP transport deferral) continue to apply.
