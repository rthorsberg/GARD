<!--
SYNC IMPACT REPORT
==================
Version change: (template, unratified) → 1.0.0
Bump rationale: First ratified constitution for GARD. MAJOR baseline because all
principles, governance and section structure are introduced as binding rules.

Modified principles:
  - (template placeholder I)   → I.   Governance Before Execution
  - (template placeholder II)  → II.  Desired State and Actual State Are Separate
  - (template placeholder III) → III. Unknown Is a First-Class Lifecycle State
  - (template placeholder IV)  → IV.  Lifecycle-as-Code
  - (template placeholder V)   → V.   Evidence, Audit & Explainability (NON-NEGOTIABLE)
  - (added)                    → VI.  MCP Exposes Curated Tools, Not Raw Infrastructure
  - (added)                    → VII. Integration Over Replacement

Added sections:
  - Additional Constraints (Security, Quality & Testing, Architecture Boundaries)
  - Development Workflow & Quality Gates
  - Governance

Removed sections:
  - All bracketed placeholder slots from the template

Templates requiring updates:
  - ✅ .specify/templates/constitution-template.md  (source template, unchanged)
  - ✅ .specify/templates/plan-template.md          (uses generic Constitution Check
                                                     gate; no edit needed — gates
                                                     evaluated against this file at
                                                     plan time)
  - ✅ .specify/templates/spec-template.md          (no constitution-coupled fields)
  - ✅ .specify/templates/tasks-template.md         (no constitution-coupled fields)
  - ✅ .specify/templates/checklist-template.md     (no constitution-coupled fields)
  - ✅ .cursor/rules/specify-rules.mdc              (already references current plan;
                                                     no edit needed)

Follow-up TODOs:
  - None. All placeholders resolved.
-->

# GARD Constitution

> **GARD** — Service Lifecycle Guardrails. An MCP-native firmware/software
> lifecycle governance platform for Communication Service Provider (CSP) network
> infrastructure. This document is the binding charter for how GARD is designed,
> built, reviewed and evolved. It supersedes all conflicting practice; conflicts
> with ADRs, plans, specs or code are resolved in favor of this constitution
> until it is formally amended.

## Core Principles

### I. Governance Before Execution

GARD MUST treat lifecycle governance — observe, compare, plan, approve, verify,
evidence, reconcile — as the product's primary surface. v1 MUST NOT perform
uncontrolled autonomous execution of device changes; uplift MUST be guided or
semi-automated and gated by an explicit human (or delegated, audited)
approval. Any feature that would let an actor (human, system, or AI agent)
mutate device state without an approval gate and an audit record is a
constitutional violation.

**Rationale**: Firmware uplift in CSP networks carries operational risk; the
product's value is governed change, not faster unsupervised change.
See ADR-0002.

### II. Desired State and Actual State Are Separate

GARD MUST model **desired state** (FirmwareTarget, upgrade paths,
prerequisites, policies) and **actual state** (DeviceObservation) as
independent, separately-sourced records. Drift, risk and readiness MUST be
**derived** signals computed from these inputs — never stored as authoritative
truth and never silently mutated by adapters or background jobs. Controllers
MUST be the only writers of derived state, and each derived value MUST cite
the inputs that produced it.

**Rationale**: A controller-style separation (Terraform/Kubernetes/SDN
heritage) is what makes drift, plans and evidence auditable and reproducible.
See `specs/03-architecture.md`.

### III. Unknown Is a First-Class Lifecycle State

`unknown` MUST be a representable, queryable, reportable lifecycle state for
every dimension that can be missing: current firmware, target firmware,
upgrade path, prerequisite outcome, readiness, and risk. Code MUST NOT
substitute defaults, "best guesses", or empty strings for missing data, and
MUST NOT silently exclude unknown rows from compliance or readiness counts.
Reports and MCP responses MUST surface unknown counts alongside known
classifications.

**Rationale**: The North Star is "No device left unknown." Hiding unknowns
defeats the product. See PRD §5 and `context/01-domain-assumptions.md`.

### IV. Lifecycle-as-Code

Lifecycle catalogues — firmware targets, firmware packages (metadata),
upgrade paths, prerequisite rules, normalization rules, command templates,
and policies — MUST be expressible as version-controlled files with a
declared schema. The runtime MUST be able to load these catalogues from a
Git-managed source, and any UI/API edit MUST be exportable back to that
file format. Schema-breaking catalogue changes MUST follow the same
versioning discipline as code (see Governance).

**Rationale**: Catalogues are critical lifecycle knowledge; UI-only storage
loses reviewability, diffability and change control. See ADR-0004.

### V. Evidence, Audit & Explainability (NON-NEGOTIABLE)

Every critical lifecycle event — import, normalization rule change, target
change, package upload, checksum verification, prerequisite rule change,
compliance evaluation, readiness evaluation, plan creation, wave creation,
approval, execution start, execution result, exception approval, MCP call
that mutates state, API write — MUST produce both:

1. an append-only `AuditEvent` (actor, action, object, before/after,
   correlation id, result), and
2. where it concerns device lifecycle outcomes, a structured
   `LifecycleEvidence` record.

Every classification (`compliant` / `outside target` / `unknown` / `blocked`
/ `ready`) and every plan step MUST be **explainable**: the response MUST
cite the rule, target, observation and policy that produced it. "Because the
system said so" is not an acceptable answer surface.

**Rationale**: This is what separates GARD from a script. Without verifiable
evidence and explainability, governance is theatre. See
`specs/08-security-rbac-audit.md`.

### VI. MCP Exposes Curated Tools, Not Raw Infrastructure

The MCP server MUST expose only purpose-built, schema-validated lifecycle
tools. It MUST NOT expose raw SQL, raw shell, arbitrary HTTP, file-system, or
unrestricted CLI access to agents. Each MCP tool MUST be subject to the same
RBAC and audit pipeline as the REST API, MUST declare whether it is
read-only or state-mutating, and any state-mutating tool MUST flow through
the same approval gates as a human actor.

**Rationale**: Agent ergonomics MUST NOT compromise governance. See ADR-0003
and the anti-goal "no raw SQL/shell backend for AI agents".

### VII. Integration Over Replacement

GARD MUST integrate with existing domain systems rather than reinvent them.
Specifically: NetBox (or an equivalent inventory system) remains
authoritative for **infrastructure identity/reference**; TR-069/TR-369 ACS,
NETCONF, CLI, NSO, Ansible/Nornir and vendor APIs are **southbound execution
adapters**, not GARD-internal capabilities. GARD owns lifecycle policy,
target state, drift, risk, readiness, planning, approval and evidence.
Anti-goals (CMDB replacement, monitoring system, ACS replacement) are
binding.

**Rationale**: Replacing adjacent systems expands scope, weakens trust with
operators, and dilutes the lifecycle-governance value proposition. See
ADR-0001 and ADR-0005.

## Additional Constraints

### Security

- Secrets (device credentials, adapter credentials, signing keys) MUST be
  retrieved from a secret manager (e.g., Vault) at use time and MUST NOT be
  persisted in the application database in plain text.
- RBAC MUST separate `read`, `plan`, `approve` and `execute` permissions;
  no single role may both create and approve the same wave or exception in
  production.
- Firmware packages MUST carry checksum metadata, MUST be checksum-verified
  before being referenced by an approved plan, and MUST NOT be usable in an
  approved wave without explicit, audited exception otherwise.
- The audit log MUST be append-only at the application layer.

### Quality & Testing

GARD adopts a **contract-and-integration-first** testing posture:

- Every controller boundary, REST endpoint, MCP tool, importer, adapter and
  catalogue schema MUST have contract tests that fail when the contract
  changes without an intentional version bump.
- Integration tests are MANDATORY for: CSV import, normalization,
  compliance/readiness evaluation, plan generation, approval flow, evidence
  emission, and any new MCP tool.
- Unit tests are RECOMMENDED for non-trivial pure logic (rule engines,
  version comparators, drift classifiers).
- TDD is encouraged but NOT mandated. A change MUST NOT merge with red
  contract or integration tests on the changed surface.

### Architecture Boundaries

- Core controllers MUST NOT call southbound adapters directly; adapter
  invocation MUST go through a defined adapter interface with its own
  auth, audit and timeout policy.
- Cross-controller data flow MUST be via persisted state or explicit events,
  not in-process shared mutable state.
- Tech-stack choices (database, runtime, deployment topology) are governed
  by ADRs, not by this constitution. The constitution constrains *behavior*
  (audit, approval, evidence, separation of state), not *implementation
  technology*.

## Development Workflow & Quality Gates

- Every feature MUST proceed through the Spec Kit flow: `specify → clarify
  (when needed) → plan → tasks → implement`, with the plan template's
  **Constitution Check** gate evaluated against this file before Phase 0
  and re-evaluated after Phase 1 design.
- Plans MUST list, per principle, whether the feature complies, requires
  exception, or extends the principle. Exceptions MUST be justified in the
  plan's Complexity Tracking section and approved before implementation.
- Pull requests MUST link to (a) the spec, (b) the plan, and (c) any ADR
  the change creates or modifies. Changes that touch lifecycle classification,
  approval, evidence, audit, MCP tool surface, or RBAC require review by a
  reviewer outside the change author's immediate working scope.
- Schema-breaking changes to catalogues, REST contracts or MCP tools MUST
  ship with a migration note and a version bump (see Governance).
- Observability: structured logs MUST carry the `correlation_id` used by the
  audit pipeline so a request can be traced from API/MCP call to evidence.

## Governance

This constitution supersedes all other engineering practice within the GARD
project. ADRs, plans, specs and code MUST conform; conflicts are resolved in
favor of this constitution until it is formally amended.

**Amendment procedure**:

1. Open a PR modifying `.specify/memory/constitution.md` with a Sync Impact
   Report at the top describing the change, version bump rationale, and any
   dependent template/doc updates.
2. The PR MUST update the version line and the `Last Amended` date.
3. The PR MUST list which ADRs, templates, or runtime docs are affected and
   either update them in the same PR or open tracking issues.
4. Approval requires at least one reviewer who did not author the
   amendment.

**Versioning policy** (semantic versioning of the constitution itself):

- **MAJOR**: Removing a principle, redefining a principle in a backward-
  incompatible way, or weakening a non-negotiable rule (e.g., relaxing
  audit/evidence requirements, allowing autonomous execution in v1).
- **MINOR**: Adding a new principle or section, or materially expanding
  guidance under an existing principle.
- **PATCH**: Clarifications, wording fixes, typos, and non-semantic
  refinements that do not change what is required, prohibited or permitted.

**Compliance review**: The Constitution Check gate in
`.specify/templates/plan-template.md` is the primary enforcement point.
Reviewers MUST treat unjustified Constitution Check failures as blocking.
At minimum once per release cycle, maintainers SHOULD review whether
accumulated exceptions indicate that the constitution itself needs amendment.

**Runtime guidance**: The active feature plan in
`.specify/memory/` and the Spec Kit templates in `.specify/templates/`
provide day-to-day development guidance and MUST remain consistent with this
document.

**Version**: 1.0.0 | **Ratified**: 2026-05-27 | **Last Amended**: 2026-05-27
