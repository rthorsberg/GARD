# F6 — MVP Vertical Slice Validation (Cisco ISR1121): Implementation Plan

**Feature Branch**: `006-mvp-vertical-slice-cisco-isr1121`
**Status**: Draft
**Inputs**: `spec.md`, `research.md` (R-1..R-5), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F1–F5 (all shipped on `main` as of 2026-05-31)
**Successor**: F7 — NetBox Integration (read-only)

## Summary

F6 is a **validation feature**: it adds ISR1121-specific catalog fixtures, a CSV fixture, one golden-path integration test suite, MCP delegate assertions, an operator runbook, and a sibling seed script — without new REST endpoints, ORM entities, or lifecycle states.

The technical shape:

- **Catalog additions** under `gard-catalog/firmware/` for Cisco ISR1121 (target, packages, upgrade path, prerequisite rules) derived from `gard-speckit-start/examples/`.
- **Fixture CSV** at `deploy/scripts/fixtures/isr1121-devices.csv` mapped to the F1 import contract.
- **Integration test** `tests/integration/test_mvp_vertical_slice_isr1121.py` asserting all ten MVP acceptance criteria.
- **Helper module** `tests/integration/_mvp_isr1121_helpers.py` — factory loading catalog + CSV + tokens (drafter + approver).
- **Runbook** `specs/006-mvp-vertical-slice-cisco-isr1121/quickstart.md` + **`deploy/scripts/seed-isr1121.sh`** sibling to generic `seed.sh`.
- **Contract** `contracts/acceptance-matrix.yaml` — criterion → test mapping for reviewers.

## Technical Context

| Aspect | Choice |
|---|---|
| Runtime | Python 3.12 + FastAPI (unchanged) |
| DB | PostgreSQL 16 (existing CI + Docker) |
| Tests | pytest integration module + reuse of existing contract tests where possible |
| Catalog | Extend `gard-catalog/` only; no schema changes |
| MCP | Delegate invocation only (ADR-0013 transport still deferred) |
| Performance | Vertical-slice test target < 60s wall time; CI budget +90s max |
| Scope guard | Zero new migrations, routers, or models |

## Constitution Check

| Principle | F6 adherence |
|---|---|
| I — Governance Before Execution | Golden path stops at `approved`; no execution assertions. |
| II — Desired vs Actual | Test verifies derived compliance/readiness from catalog + observations. |
| III — Unknown Is First-Class | Fixture includes at least one non-ISR1121 or ambiguous row to prove filtering; ISR1121 path avoids `unknown` by catalog completeness. |
| IV — Lifecycle-as-Code | Catalog YAML is the desired-state source; test reloads via existing F2 pipeline. |
| V — Evidence/Audit/Explainability | User Story 4 asserts audit chain + citation preservation on approval. |
| VI — Curated MCP Tools | Delegate tests only; no new tools unless gap found. |
| VII — Integration Over Replacement | No NetBox, no adapters — pure in-repo validation. |

All seven principles pass. F6 adds no constitutional exceptions.

## Project Structure (new + extended files)

**Specs / contracts**

- `specs/006-mvp-vertical-slice-cisco-isr1121/spec.md` (new)
- `specs/006-mvp-vertical-slice-cisco-isr1121/plan.md` (this file)
- `specs/006-mvp-vertical-slice-cisco-isr1121/research.md` (new)
- `specs/006-mvp-vertical-slice-cisco-isr1121/data-model.md` (new)
- `specs/006-mvp-vertical-slice-cisco-isr1121/quickstart.md` (new)
- `specs/006-mvp-vertical-slice-cisco-isr1121/contracts/acceptance-matrix.yaml` (new)
- `specs/006-mvp-vertical-slice-cisco-isr1121/tasks.md` (Phase 2 — `/speckit-tasks`)

**Catalog fixtures**

- `gard-catalog/firmware/targets/cisco-ios-isr1121.yaml` (new)
- `gard-catalog/firmware/packages/cisco-ios-17.12.4.yaml` (new)
- `gard-catalog/firmware/packages/cisco-ios-16.9.5.yaml` (new)
- `gard-catalog/firmware/upgrade-paths/cisco-ios-isr1121.yaml` (new)
- `gard-catalog/firmware/prerequisites/isr1121-minimum-flash.yaml` (new)

**Deploy / fixtures**

- `deploy/scripts/fixtures/isr1121-devices.csv` (new)
- `deploy/scripts/seed-isr1121.sh` (new)

**Tests**

- `tests/integration/_mvp_isr1121_helpers.py` (new)
- `tests/integration/test_mvp_vertical_slice_isr1121.py` (new)

**Docs**

- `README.md` (extend — F6 status)
- `ROADMAP.md` (extend — F6 in progress)
- `.cursor/rules/specify-rules.mdc` (point active plan at F6)

## PR slices

| Slice | Scope | Exit criteria |
|---|---|---|
| **6a** | Spec + plan + research + acceptance matrix + catalog/fixture scaffolding | Design artifacts committed; catalog loads without error |
| **6b** | Integration test + helpers; CI green | All ten MVP criteria asserted in pytest |
| **6c** | Runbook + `seed-isr1121.sh` + README/ROADMAP | Manual Docker walkthrough matches automated path |

## Complexity Tracking

No constitution violations. Table intentionally empty.

## Phase 0 — Research (complete)

See `research.md` for R-1..R-5 binding decisions.

## Phase 1 — Design artifacts (complete)

- `data-model.md` — fixture entity map (no new tables)
- `contracts/acceptance-matrix.yaml` — criterion → assertion mapping
- `quickstart.md` — operator runbook

## Phase 2 — Tasks

Run `/speckit-tasks` to generate `tasks.md` before implementation.
