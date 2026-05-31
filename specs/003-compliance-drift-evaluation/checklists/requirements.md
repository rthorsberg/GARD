# Specification Quality Checklist: F3 — Compliance & Drift Evaluation

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-30
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
  *Note: REST paths and JSON field names are part of the public contract — see Quick Guidelines exception for API surfaces.*
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## F3-specific quality probes

- [x] Drift taxonomy enumerated and grounded in seed material (`gard-speckit-start/specs/02-lifecycle-state-machine.md` §"Drift Taxonomy")
- [x] Composition with F2's `FirmwareComplianceEnvelope` made explicit (FR-006)
- [x] Determinism guarantee for envelope serialisation stated (FR-010, SC-005)
- [x] Forward seam to F5 (Exception entity) called out and bounded (FR-021, Assumption)
- [x] MCP deferral consistent with ADR-0013 — F3 ships contracts only (FR-025, FR-026, US3)
- [x] Constitution III (never coerce missing data) preserved — `unknown` keeps its own counter, not folded into a drift bucket (Edge Cases)
- [x] Performance budget for the headline endpoint is quantified (SC-001, 1s p95 over 5,000 devices)

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- F3 spec was drafted in one pass with zero `[NEEDS CLARIFICATION]` markers — front-loaded by reading F2's envelope code and the seed drift taxonomy directly.
- The biggest planning-time question (which is *not* a spec ambiguity) is whether `ComplianceEvaluation` rows live in `gard_app` (mutable) or are append-only via the audit-grade `lifecycle_evidence` table. That is a plan-level design choice; FR-004 fixes the append-only semantics either way.
