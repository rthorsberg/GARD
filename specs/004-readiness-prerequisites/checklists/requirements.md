# Specification Quality Checklist: Readiness & Prerequisites (F4)

**Purpose**: Validate specification completeness and quality before proceeding to planning.
**Created**: 2026-05-31
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
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
- [x] User scenarios cover primary flows (US1 estate summary, US2 per-device verdict, US3 MCP)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## F4-specific quality probes

- [x] Readiness state taxonomy enumerated explicitly (`ready_for_uplift`, `blocked`, `not_applicable`) and the biconditional rules for each are stated (FR-003, FR-004).
- [x] Cross-feature reads (F2 prerequisite catalogue, F2 upgrade-path graph, F3 compliance row) are named in `Dependencies`; no implicit data sources.
- [x] Edge cases for missing inputs, missing rules, stale F3 inputs, deferred predicates, multi-rule conflicts, and `not_applicable` carve-outs are listed before requirements are read.
- [x] The 4 MCP tool contracts are named (FR-022) so plan.md can lock contracts before implementation.
- [x] Determinism + idempotency contracts (FR-015, FR-024) match F3 R-4 / R-7 — no drift between sibling features.
- [x] RBAC permissions are explicit (FR-018) and align with F3's pattern: read for viewer+, run for lifecycle_manager+.
- [x] Constitution III ("never coerce") is honored in the missing-input edge case (`missing_observation_field` blocker, never assume zero).
- [x] The forward seam (F5 exception override) is documented in Assumptions without leaking F5 implementation detail.

## Notes

- The 7 prerequisite predicate kinds inherited from F2 + 2 F4-internal synthetic kinds (`missing_upgrade_path`, `missing_observation_field`) form the closed `predicate_kind` enum the contract tests will lock.
- The 6 recommended-action kinds extend F3's vocabulary; F3's `RecommendedActionKind` Literal will need to grow. Planning will decide whether to extend in place (F3's contract test catches new kinds) or split into a sibling enum.
- "Stale F3 input" is a 409 not a 4xx — it asks the caller to refresh, not to fix the request.
