# Implementation Plan: F4 — Readiness & Prerequisites

**Branch**: `004-readiness-prerequisites` | **Date**: 2026-05-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/004-readiness-prerequisites/spec.md`

## Summary

F4 closes the gap between *"this device is off-target"* (F3) and *"this device is safe to schedule for uplift"* (F5). It runs the F2 prerequisite catalogue against every device F3 flagged as `outside_target`, checks for an upgrade-path chain to the target version, and persists a per-device verdict (`ready_for_uplift` / `blocked` / `not_applicable`) as an append-only `ReadinessEvaluation` row.

The headline endpoint — `GET /api/v1/readiness/summary` — must answer *"of the N devices that are off-target, how many can I actually schedule this quarter and what's the dominant blocker?"* in under 1 second p95 over 5,000 devices.

The technical pivot from F3: F3 classified drift across the whole estate (every device evaluated, regardless of state). F4 is more focused — it only matters for devices in F3 verdict `outside_target`. Compliant / unknown / classified devices get a `not_applicable` verdict cheaply and exit the pipeline. The blocker check itself is the new logic: each F2 prerequisite rule whose `applies_to` selector matches the device fires its predicate against the device's observation, producing zero or more typed blockers. Plus a "reachability" check that asks F2's upgrade-path graph: "does any chain exist from `observed_version` to `target_version` on this platform whose accumulated weight is under the configured cap?"

The audit + envelope shape mirrors F3 exactly — same explainability discipline, same idempotency contract, same DISTINCT-ON read pattern for the summary. The new MCP tools (`get_readiness_summary`, `list_blocked_devices`, `explain_blockers`, `get_ready_for_uplift_devices`) ship as delegates only; transport stays deferred to F008.

## Technical Context

**Language/Version**: Python 3.12 (ADR-0006).
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, structlog, `networkx` (already pulled in by F2; F4 reuses `UpgradePathGraphCache`).
**Storage**: PostgreSQL 16. New table `gard_app.readiness_evaluations` (append-only at row level). F4 reads F1's `device_observations`, F2's `firmware_prerequisite_rules` + `firmware_upgrade_paths`, F3's `compliance_evaluations`. Audit emissions land in `gard_audit.audit_events` via the existing append-only writer session (ADR-0009).
**Testing**: pytest. Same three-layer convention: `tests/unit/test_prereq_predicates.py` for pure predicate logic, `tests/unit/test_readiness_controller.py` for composition, `tests/contract/test_readiness_*` for OpenAPI + MCP-tool lock, `tests/integration/test_us*` for end-to-end against compose Postgres.
**Target Platform**: Same `gard-api` Docker image. No new platform surface.
**Project Type**: Web service (single-project layout).
**Performance Goals**:
  - `GET /api/v1/readiness/summary` p95 < 1 s over 5,000 devices × 50 prerequisite rules (SC-001).
  - `GET /api/v1/readiness/devices?…` p95 < 500 ms for 50-row pages.
  - `POST /api/v1/readiness/evaluate` linear in batch size, capped at 5,000 (FR-013).
**Constraints**:
  - Summary endpoint MUST read only from persisted `ReadinessEvaluation` rows; it MUST NOT trigger per-device evaluation on the hot path (FR-011).
  - Evaluation MUST be derived from the LATEST persisted F3 `ComplianceEvaluation` row per device — F4 never re-queries F2 directly for target/observed.
  - Envelope serialisation MUST be deterministic given identical inputs, modulo `correlation_id` / `as_of` (FR-024).
  - F4 MUST NOT mutate F1's, F2's, or F3's tables. The lifecycle_state transition (`outside_target → ready_for_uplift` / `blocked`) IS a write to `devices` — that one mutation is justified because the lifecycle state machine is a cross-feature responsibility documented in `gard-speckit-start/specs/02-lifecycle-state-machine.md`.
**Scale/Scope**: v1 design target is 5,000 devices, 50 prerequisite rules, 200 upgrade-path edges. 10× headroom without index changes.

## Constitution Check

| Principle | Status | How this plan complies |
|---|---|---|
| I. Governance Before Execution | ✅ | F4 introduces zero adapter/device-mutation surfaces. The only writes F4 owns are `readiness_evaluations` (its own table), `audit_events` (append-only), and one specific lifecycle_state column update per device on verdict change. `POST /readiness/evaluate` *re-evaluates*; it does not push anything to any device. |
| II. Desired ↔ Actual State Separation | ✅ | `ReadinessEvaluation` is **derived state**: it joins desired state (F2 prereqs + F2 graph) against actual state (F1 observations) under the F3-defined drift envelope. Re-running the controller from the same inputs always reproduces the same verdict (SC-004). |
| III. Unknown Is First-Class | ✅ | Missing observation fields surface as `kind=missing_observation_field` blockers (with `severity=required` when the rule depends on them). F4 NEVER assumes a missing input is zero or absent. `not_applicable` is itself a first-class verdict for devices F4 has nothing useful to say about. |
| IV. Lifecycle-as-Code | ✅ | F4 adds **no new YAML files**. It consumes F2's `firmware_prerequisite_rules` and `firmware_upgrade_paths`. The two new configurations (`GARD_READINESS_STALE_DAYS`, `GARD_READINESS_UPGRADE_WEIGHT_CAP`) are env vars with documented defaults, following F1/F2/F3 convention. |
| V. Evidence, Audit & Explainability (NON-NEGOTIABLE) | ✅ | Three audit families: `readiness.evaluated` (per controller invocation per device whose verdict changed), `readiness.read` (per summary/list request), `readiness.evaluation_triggered` (per `POST /readiness/evaluate`). Every blocker in the envelope cites either a `rule_id` (when from F2's catalogue) or a closed-enum `predicate_kind` (when synthetic). Determinism is enforced via stable sort on `(severity desc, predicate_kind, rule_id)` for blockers and `(kind, JSON payload)` for actions (FR-024). |
| VI. MCP Exposes Curated Tools, Not Raw Infrastructure | ✅ | F4 publishes **four** read-only tool contracts: `get_readiness_summary`, `list_blocked_devices`, `explain_blockers`, `get_ready_for_uplift_devices`. Inputs are bounded (max 500 list items, no free-form SQL). Transport itself stays deferred to F008 per ADR-0013; F4 ships contracts + delegates. |
| VII. Integration Over Replacement | ✅ | F4 reads F1/F2/F3 entities via SQLAlchemy. No replacement of F3's drift envelope; F4 extends it. The exception-override seam (FR-021 assumption "F5 will handle") is a forward seam to F5 — v1 evaluates it as "no exception". NetBox-derived facts come through F1 as already-imported columns; F7 owns the NetBox boundary, not F4. |

**Additional Constraints**:
- F4 widens F3's `RecommendedActionKind` Literal in place (R-2 decision). Contract test on F3's OpenAPI will catch the addition and force the schema to reflect it — that's a feature, not a problem.
- Reload-sync is *not* a new hook. F4 extends F3's existing `_reevaluate_compliance_post_reload` so the same N devices get both F3 and F4 re-evaluation in the same pass.

## Project Structure

Files added or extended in F4 (paths relative to repo root):

```
adr/
├── ADR-0015-readiness-verdict-precedence.md   # new — precedence + biconditional rules

gard/
├── core/
│   ├── prereq_predicates.py                   # new — one pure fn per predicate_kind
│   ├── readiness_evaluation_controller.py     # new — F4 controller (compose F3 + predicates + graph)
│   ├── envelope.py                            # extend — add ReadinessEnvelope + ReadinessState
│   ├── recommended_actions.py                 # extend — add 4 new builders
│   ├── rbac.py                                # extend — READ_READINESS / RUN_READINESS_EVAL
│   ├── settings.py                            # extend — STALE_DAYS / UPGRADE_WEIGHT_CAP
│   └── firmware_catalog_controller.py         # extend — reload hook also calls F4
├── db/migrations/versions/
│   └── 0008_readiness_evaluations.py          # new — table + indices
├── models/
│   ├── readiness_evaluation.py                # new
│   └── __init__.py                            # extend — register model
├── api/
│   ├── schemas/
│   │   └── readiness.py                       # new — Pydantic surface
│   ├── routers/
│   │   └── readiness.py                       # new — 4 endpoints
│   └── app.py                                 # extend — register router
└── mcp/tools/
    ├── get_readiness_summary.py               # new
    ├── list_blocked_devices.py                # new
    ├── explain_blockers.py                    # new
    └── get_ready_for_uplift_devices.py        # new

specs/004-readiness-prerequisites/
├── spec.md                                    # ✅ done
├── checklists/requirements.md                 # ✅ done
├── plan.md                                    # this file
├── research.md                                # Phase 0 output
├── data-model.md                              # Phase 1 output
├── contracts/
│   ├── rest-openapi.yaml
│   └── mcp-tools.yaml
├── quickstart.md
└── tasks.md                                   # /speckit-tasks output

tests/
├── unit/
│   ├── test_prereq_predicates.py
│   └── test_readiness_controller.py
├── contract/
│   ├── test_readiness_rest_openapi.py
│   └── test_readiness_mcp_tools.py
└── integration/
    ├── test_us1_readiness_summary.py
    └── test_us2_explainable_blockers.py

deploy/scripts/
└── seed.sh                                    # extend — add F4 walk

gard-catalog/firmware/prerequisites/
└── (extend with 1–2 new fixtures so seeded fixtures exercise the blocker path)
```

## Complexity Tracking

*Nothing flagged here — F4 stays within the patterns F3 established.*

## Phase 0: Outline & Research

Output: [research.md](./research.md).

Eight binding decisions (R-1 .. R-8) — precedence ordering for blocker severity, storage shape, evaluator composition, action vocabulary extension strategy, summary query strategy, reload-sync extension, determinism, stale-input handling. All decisions ground out in F1/F2/F3 patterns where one applies.

## Phase 1: Design & Contracts

Outputs:

- [data-model.md](./data-model.md) — `ReadinessEvaluation` table, JSONB blocker shape, audit emit catalogue, state-transition matrix vs F3.
- [contracts/rest-openapi.yaml](./contracts/rest-openapi.yaml) — 4 REST endpoints (`/readiness/summary`, `/readiness/devices`, `/devices/{id}/readiness`, `/readiness/evaluate`) with full request/response schemas.
- [contracts/mcp-tools.yaml](./contracts/mcp-tools.yaml) — 4 read-only MCP tools with input/output schemas + auth strings.
- [quickstart.md](./quickstart.md) — operator workflow against the seeded fixture (estate readiness summary → drill into one blocked device → trigger re-evaluation after a prereq rule change).

Phase 1 ends with the constitution check re-applied; no principle is at risk.
