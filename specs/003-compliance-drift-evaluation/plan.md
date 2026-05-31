# Implementation Plan: F3 — Compliance & Drift Evaluation

**Branch**: `003-compliance-drift-evaluation` | **Date**: 2026-05-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-compliance-drift-evaluation/spec.md`

## Summary

F3 turns GARD from a per-device firmware checker into an **estate-wide
drift control plane**. It does so by classifying every device into one
or more of seven **drift types** (target / catalog / package / rule /
evidence / discovery / exception), persisting the classification as an
append-only `ComplianceEvaluation` row, and serving it through three
read endpoints and four MCP tool contracts. The headline operator
endpoint — `GET /api/v1/compliance/summary` — must answer "where is
my drift, by category, across 5,000 devices" in under 1 second at
p95.

The technical pivot from F2: F2 evaluated compliance on the *write*
path (the bounded re-eval pipeline) and served the latest result
synchronously per device. F3 keeps that pipeline (no replacement),
adds **persisted evaluation rows** so summary/listing endpoints can
serve from indexed reads without touching the hot per-device path,
and extends F2's `FirmwareComplianceEnvelope` with the typed
`drift_type` + non-empty `recommended_actions[]` that F2 left as
empty seams.

## Technical Context

**Language/Version**: Python 3.12 (locked in ADR-0006 during F1)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic
v2, structlog, `networkx` (already pulled in by F2 for upgrade-path
queries; F3 does not add it again)
**Storage**: PostgreSQL 16 — `gard_app.compliance_evaluations` (new
table, append-only at row level), plus reads against F1's `devices` /
`device_observations` and F2's catalog tables. Audit emissions land
in `gard_audit.audit_events` via the existing append-only writer
session (ADR-0009).
**Testing**: pytest with `pytest-asyncio`. Three layers consistent
with F1/F2 — `tests/unit/` for pure-function controllers and
predicates, `tests/contract/` for JSON-schema and OpenAPI conformance,
`tests/integration/` for end-to-end against the compose Postgres.
**Target Platform**: Linux x86_64 / arm64 server runtime via the
existing `gard-api` Docker image. No new platform surface.
**Project Type**: Web service (single project layout per F1's
decision — `gard/` package + `tests/` + `deploy/`).
**Performance Goals**:
  - `GET /api/v1/compliance/summary` p95 < 1 s over 5,000 devices ×
    200 targets (SC-001)
  - `GET /api/v1/compliance/devices?…` p95 < 500 ms for 50-row pages
  - `POST /api/v1/compliance/evaluate` linear in batch size, with a
    hard cap of 5,000 devices per call (FR-014); refusing larger sets
    keeps tail latency bounded
**Constraints**:
  - Summary endpoint MUST read only from persisted
    `ComplianceEvaluation` rows; it MUST NOT trigger per-device
    evaluation on the read path (FR-013, SC-008)
  - Envelope serialisation MUST be deterministic given identical
    inputs, modulo `correlation_id` / `as_of` (FR-010, SC-005)
  - Cross-feature respect: F3 MUST NOT mutate F2's
    `firmware_targets`, `firmware_packages`, `firmware_upgrade_paths`,
    or `firmware_prerequisite_rules` tables. F3 is a pure consumer.
**Scale/Scope**: v1 design target is 5,000 devices and 200 targets;
table layout sized for 10× headroom without index-scheme changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1
design.*

| Principle | Status | How this plan complies |
|---|---|---|
| I. Governance Before Execution | ✅ | F3 introduces zero adapter / device-mutation surfaces. Every endpoint is read-only on infrastructure identity; the only F3-owned writes are to its own `compliance_evaluations` table and to audit/evidence (append-only by DB grants). `POST /compliance/evaluate` *triggers* re-evaluation but does not push state to any device. |
| II. Desired ↔ Actual State Separation | ✅ | `ComplianceEvaluation` is **derived state**, computed by reading desired state (F2's `firmware_targets`) and actual state (F1's `device_observations`). The row is a snapshot of a derivation, not a substitute for either source. Re-running the controller from the same inputs always reproduces the same envelope (SC-005). |
| III. Unknown Is First-Class | ✅ | The `unknown` lifecycle state from F2 (ADR-0012) keeps its own bucket in the summary (`unknown_count`) — it is **not** folded into any drift type. Devices with no observation surface `discovery_drift` of kind `missing_observation` with `observed_version: null` rather than coercing the absence to a string. Confidence drops to F1's `manual_review_required` mapping (0.0) when the verdict rests on missing inputs. |
| IV. Lifecycle-as-Code | ✅ | F3 adds **no new YAML catalogue files** of its own. It consumes the F2 catalog. Two new configurations — staleness thresholds for `discovery_drift` / `evidence_drift` — are environment variables (`GARD_DISCOVERY_STALE_DAYS`, `GARD_EVIDENCE_STALE_DAYS`) with documented defaults, following F1/F2 convention. The drift precedence ordering (the highest-impact rule choice) is captured in ADR-0014 rather than a code constant alone. |
| V. Evidence, Audit & Explainability (NON-NEGOTIABLE) | ✅ | This is **the feature** that delivers Principle V. Three audit families are emitted: `compliance.evaluated` (one row per controller invocation per device), `compliance.read` (one row per summary/list request with the resolved filter set), and `compliance.evaluation_triggered` (one row per `POST /compliance/evaluate` with the resolved device-id set capped at 100 echoed back). Every envelope's `reasons[]` cites contributing artefacts by stable id (target id, observation id, catalog file relpath, policy-decision key). Determinism is enforced by sorting `reasons[]` and `recommended_actions[]` on `kind` then `ref` (FR-010). |
| VI. MCP Exposes Curated Tools, Not Raw Infrastructure | ✅ | F3 publishes **four** read-only tool contracts in `contracts/mcp-tools.yaml` — `count_devices_outside_target`, `list_devices_outside_target`, `get_compliance_summary`, `get_unknown_lifecycle_items`. Inputs are bounded (max 500 list items, no free-form SQL or selector strings — predicate fields are explicit Pydantic models). The MCP transport itself remains deferred to feature 008 per ADR-0013; F3 ships contracts + delegate implementations with REST-parity unit tests so the eventual transport feature is a thin port. |
| VII. Integration Over Replacement | ✅ | F3 reads F1 and F2 entities as-is via SQLAlchemy. No replacement of either feature's responsibilities. The `Exception` rule in FR-021 is a forward seam to F5; F3 implements it as a predicate that returns "no exception" until F5 adds the entity. NetBox-derived facts (region/site/role from F1 import) are filterable parameters, not new pulls from NetBox; F7 will own the NetBox boundary. |

**Additional Constraints**:
- **Security**: No new secret; no new external network call. RBAC adds two
  permissions (`READ_COMPLIANCE`, `RUN_COMPLIANCE_EVAL`) following F2's
  assignment pattern (analyst/auditor get read; lifecycle_manager
  gains both; system_admin gains both).
- **Quality**: Every new contract surface gets a contract test:
  REST OpenAPI conformance, MCP tool JSON schemas, and per-drift-rule
  unit tests covering the truth table (rule input → drift type
  classification).
- **Architecture Boundaries**: `compliance_evaluation_controller`
  composes over F2's `compliance_controller` and `upgrade_path_graph`
  (for `rule_drift`). It does NOT directly read F2's YAML loader,
  call subprocess, or touch the blob store. The only cross-feature
  call into F3 is the bounded-reeval hook F2 already wired: after a
  successful reload, F2 will additionally invoke
  `compliance_evaluation_controller.reevaluate_for_devices(...)` over
  the same bounded set, so the persisted F3 rows stay in sync without
  F3 owning the reload trigger.

**Result**: **PASS — all 7 principles satisfied, no justified violations needed.** Complexity Tracking section omitted.

## Project Structure

### Documentation (this feature)

```text
specs/003-compliance-drift-evaluation/
├── spec.md                  # /speckit-specify output (shipped)
├── plan.md                  # This file
├── research.md              # Phase 0 output — decisions + rationales
├── data-model.md            # Phase 1 output — ComplianceEvaluation entity + indices
├── contracts/
│   ├── rest-openapi.yaml    # Phase 1 output — REST surface contract
│   └── mcp-tools.yaml       # Phase 1 output — 4 MCP tool JSON schemas
├── quickstart.md            # Phase 1 output — operator quickstart
├── checklists/
│   └── requirements.md      # /speckit-specify output (shipped)
└── tasks.md                 # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
gard/
├── api/
│   ├── routers/
│   │   └── compliance.py                # NEW (US1, US2): summary, devices list,
│   │                                    # per-device, POST evaluate
│   └── schemas/
│       └── compliance.py                # NEW: ComplianceEnvelope (extends F2),
│                                        # DriftType, RecommendedAction, summary
│                                        # response models
├── core/
│   ├── compliance_evaluation_controller.py   # NEW: classification engine, the F3
│   │                                          # composition over F2 controllers
│   ├── drift_rules.py                         # NEW: one pure function per rule
│   │                                          # (target_drift, catalog_drift, ...)
│   ├── recommended_actions.py                 # NEW: action-builder per drift type
│   ├── envelope.py                            # MODIFIED (additive): ComplianceEnvelope
│   │                                          # subclass with typed drift_type +
│   │                                          # recommended_actions
│   └── rbac.py                                # MODIFIED (additive): two new permissions
├── db/
│   └── migrations/versions/
│       └── 0007_compliance_evaluations.py     # NEW: creates compliance_evaluations
│                                              # table + indices
├── mcp/
│   └── tools/
│       ├── count_devices_outside_target.py    # NEW (US3): contract + delegate
│       ├── list_devices_outside_target.py     # NEW (US3)
│       ├── get_compliance_summary.py          # NEW (US3)
│       └── get_unknown_lifecycle_items.py     # NEW (US3)
└── models/
    └── compliance_evaluation.py               # NEW: ORM model

tests/
├── unit/
│   ├── test_drift_rules.py                    # NEW: one truth table per rule
│   ├── test_recommended_actions.py            # NEW: action-kind exhaustiveness
│   └── test_compliance_envelope.py            # NEW: determinism + serialisation
├── contract/
│   ├── test_compliance_rest_openapi.py        # NEW: lock REST shape
│   └── test_compliance_mcp_tools.py           # NEW: lock 4 tool schemas
└── integration/
    ├── test_us1_summary_endpoint.py           # NEW: estate-wide drift dashboard
    ├── test_us2_explainable_envelope.py       # NEW: per-device verdict
    ├── test_us3_mcp_parity.py                 # NEW: MCP delegates match REST
    └── test_post_reload_compliance_sync.py    # NEW: F2 reload triggers F3 re-eval
                                               #      for affected devices only
```

**Structure Decision**: Same single-project Python package layout as
F1 and F2. F3 adds one router file, two new core modules
(controller + rules), one new ORM model + migration, one MCP tools
package directory, and one additive edit to `envelope.py` (the typed
`ComplianceEnvelope` extending F2's `FirmwareComplianceEnvelope`).
No new top-level directories. No new languages. No new build steps.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations — section intentionally empty.*

---

## Phase 0: Outline & Research

**Generated**: `research.md` (see [research.md](./research.md)).

Key decisions resolved during Phase 0:

| ID | Decision | Captured in |
|---|---|---|
| R-1 | `ComplianceEvaluation` storage shape | research.md §1 → ADR-0014 |
| R-2 | Drift precedence ordering | research.md §2 → ADR-0014 |
| R-3 | Summary endpoint query strategy | research.md §3 |
| R-4 | Composition with F2's compliance_controller | research.md §4 |
| R-5 | `recommended_actions[]` v1 vocabulary | research.md §5 |
| R-6 | Reload→F3 sync invocation point | research.md §6 |
| R-7 | Determinism strategy (sort keys) | research.md §7 |
| R-8 | Staleness configuration shape | research.md §8 |

**Output**: research.md with all design unknowns resolved. Zero
`NEEDS CLARIFICATION` markers remain.

## Phase 1: Design & Contracts

**Generated**: `data-model.md`, `contracts/rest-openapi.yaml`,
`contracts/mcp-tools.yaml`, `quickstart.md`.

**Entities** (full schemas in [data-model.md](./data-model.md)):

- `ComplianceEvaluation` — append-only classification row, indexed
  on `(device_id, evaluated_at DESC)` to make the latest-per-device
  read O(log n).
- `DriftType` enum and `RecommendedActionKind` enum — both
  introduced as Python `Literal` types and surfaced in the JSON
  Schema; no DB enums (CHECK-constraint pattern per F1 convention).

**Contracts** (full surfaces in `contracts/`):

- REST: 4 new paths under `/api/v1/compliance/` (summary, devices
  list, per-device, evaluate-trigger).
- MCP: 4 tool schemas, each with `input_schema`, `output_schema`,
  and `auth` permission declared.

**Agent context update**:

- `.cursor/rules/specify-rules.mdc` already points at
  `specs/001-device-import-normalize/plan.md` via the SPECKIT
  marker. F3 keeps that pointer for now — the rule is informational
  only and rewriting it on every feature branch creates merge
  noise. Will revisit once a clear convention emerges from the
  improvement-plan retrospective.

### Post-design Constitution re-check

All 7 principles still pass after Phase 1 elaborates the contracts:

- **Principle II** is reinforced by the JSON schema: every
  `ComplianceEvaluation` row carries `target_ref` as nullable and
  `observed_version` as nullable, so derived-from-nothing cases
  surface honestly.
- **Principle III** survives the test-table review — `unknown` has
  its own dedicated counter in `SummaryResponse`, no collapse path.
- **Principle V**: every emit family is declared in
  `data-model.md` §"Audit emit catalogue" with object_type +
  action + payload schema; covered by the audit-chain integration
  test.
- **Principle VI**: MCP tool JSON schemas use closed enums (no
  free-form predicate strings).

**Result**: **PASS — post-design**. No new violations introduced.

---

## Stop & Report

`/speckit-plan` ends here. Phase 2 (`tasks.md`) is produced by
`/speckit-tasks`. The plan is ready for that next step.

**Branch**: `003-compliance-drift-evaluation`
**Plan**: [specs/003-compliance-drift-evaluation/plan.md](./plan.md)
**Generated artefacts**: research.md, data-model.md,
contracts/rest-openapi.yaml, contracts/mcp-tools.yaml,
quickstart.md, plus draft ADR-0014.

**ADRs drafted during this plan** (will be moved to `adr/` and
committed alongside the implementation when F3 lands):

- ADR-0014 — Drift taxonomy formalisation: storage shape, precedence
  ordering, and the seven canonical drift types. (Drafted in
  `research.md §2`; will be promoted to `adr/ADR-0014-...md` during
  the implementation phase.)
