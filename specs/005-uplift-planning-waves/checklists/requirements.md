# F5 — Requirements quality checklist

A pre-plan gate. Every item below must be checked before plan.md is allowed to lock binding decisions.

## Scope clarity

- [x] The feature has one sentence stating *what changes* from the operator's perspective ("Operators draft, submit, approve waves of `ready_for_uplift` devices…").
- [x] The boundary with F4 is explicit: F4 owns the verdict, F5 reads it (FR-003).
- [x] The boundary with the future executor (F7+) is explicit: F5 stops at `approved`.
- [x] Out-of-scope items are named: no execution, no rollback, no real-time progress, no UI layer.

## State-machine completeness

- [x] Every state in `UpliftWave.state` is enumerated (FR-002).
- [x] Every legal transition is enumerated (FR-002).
- [x] Terminal states are explicit (`approved`, `rejected`, `cancelled` + invalidated as a special terminal).
- [x] State transitions on `lifecycle_state` are listed (US1 + US2).
- [x] Self-approval forbidden, self-rejection allowed (FR-013).
- [x] Concurrent-write outcome specified (Edge Cases + FR-002).

## Auditability (Constitution V)

- [x] Every state transition emits exactly one audit row (FR-017).
- [x] Approval citation is stored verbatim on row + in audit JSONB (FR-007 + SC-004).
- [x] Read endpoints emit `uplift.read` audit rows (FR-021).
- [x] No row is ever deleted in v1 (FR-018).
- [x] Exception expiry produces an automatic audit row (FR-012 + SC-006).

## RBAC (Constitution V + ADR-0009)

- [x] Every new permission named (FR-020).
- [x] Separation-of-duties enforced at the permission + identity level (FR-006, FR-011).
- [x] The new `change_approver` role is called out as needed.

## Determinism (Constitution V)

- [x] Device ordering inside a wave envelope is deterministic (FR-024).
- [x] Wave ordering inside a plan envelope is deterministic (FR-024).
- [x] Idempotency on submit is specified (FR-025 + SC-007).

## Performance

- [x] Wave creation + planning summary have explicit p95 targets (FR-023).
- [x] Pagination shape inherits from F3/F4 (FR-014, FR-015).

## Independent test per user story

- [x] US1: REST round-trip + audit-row assertion described.
- [x] US2: full state-machine path + self-approval guard + invalidation described.
- [x] US3: exception lifecycle + expiry behaviour described.
- [x] US4: MCP delegate metadata + contract test described.

## Constitution alignment

- [x] I — Governance: every transition is rule-bound; no operator can ad-hoc force a wave through.
- [x] II — Desired vs actual: waves are *desired* state; until F7, there is no execution side, only paper.
- [x] III — Unknown is first-class: invalidation reverdicts to F4's verdict (which may be `not_applicable` + reason `lifecycle_unknown`); never silently drop the device.
- [x] IV — Lifecycle-as-code: waves + exceptions are persisted YAML-shape Pydantic models, version-controlled via audit.
- [x] V — Evidence/audit/explainability: SC-002 enforces 1:1 transition-to-audit; SC-004 enforces citation preservation.
- [x] VI — MCP curated tools: 6 delegates, each a verb operators care about (FR-019). No raw CRUD MCP surface.
- [x] VII — Integration over replacement: F7+ handoff is purely state + audit; no executor code in F5.

## Edge cases enumerated

- [x] Device removed mid-wave.
- [x] Target version retired mid-wave.
- [x] F4 reverdict during approval window.
- [x] Concurrent approvals.
- [x] Cancellation rules per state.
- [x] Empty plan + empty wave.
- [x] Citation length bounds.
- [x] Exception-on-exception (FR-010 enum + `EXCEPTION_ALREADY_ACTIVE`).

## Sign-off

This checklist is complete. The spec is plan-ready. ADR-0016 (state machine + separation-of-duties matrix) is reserved.
