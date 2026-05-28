# GARD Roadmap

> This roadmap decomposes GARD's v1 product into a sequence of Spec Kit
> features. Each feature is one `/speckit-specify → /speckit-plan →
> /speckit-tasks → /speckit-implement` cycle, one PR series, one feature
> branch. The roadmap is a living document — when it drifts from reality,
> update it in the same PR that causes the drift.
>
> The constitution (`.specify/memory/constitution.md`) is the binding
> charter. The seed source material in `gard-speckit-start/` is the input;
> this roadmap is how we turn that material into shipped product.

## Sequencing principles

- **Foundation before features.** Audit, evidence, RBAC and the explainable
  response envelope are constitutional non-negotiables (Principle V). Every
  feature builds on a common audit/evidence pipeline, so the first feature
  must lay that pipeline down — there is no retrofit path.
- **MCP and Evidence are horizontals, not features.** Each feature
  contributes its own MCP tools and its own `LifecycleEvidence` events.
  There is no standalone "MCP feature" or "Evidence feature".
- **Vertical slices.** Each feature delivers an end-to-end capability for at
  least one reference flow, not a horizontal layer (no "all DB models
  first" feature).
- **One reference device family for v1.** Cisco ISR1121, used throughout
  the seed docs and the MCP examples. Breadth comes after the v1 vertical
  slice is green.

## v1 features

| # | Feature | Slug | Delivers | Depends on |
|---|---|---|---|---|
| F1 | Device Import & Normalize | `device-import-normalize` | CSV import endpoint; `Device` + `DeviceObservation`; normalization rule engine (lifecycle-as-code); import summary + error report; transitions `imported → classified`. **Carries the platform-foundation work** (runtime/lang ADR, Postgres + migrations, auth + RBAC scaffolding, audit pipeline with `correlation_id`, `LifecycleEvidence` schema + emit helper, structured logging, REST + MCP skeletons, Docker Compose dev env, CI). First MCP tools: `list_devices`, `get_device_lifecycle_status`. | — |
| F2 | Firmware Catalog | `firmware-catalog` | `FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule`; YAML loader (lifecycle-as-code) + API CRUD; approval workflow for targets/packages; SHA-256 checksum verification for packages. MCP tools: `get_target_firmware`, `get_upgrade_path`. | F1 |
| F3 | Compliance & Drift Evaluation | `compliance-evaluation` | `ComplianceEvaluation` controller; drift taxonomy (target / catalog / package / rule / evidence / discovery / exception drift); explainable response envelope (`state / summary / facts / reasons / recommended_actions / confidence`); transitions `target_defined → compliant / outside_target`. MCP tools: `count_devices_outside_target`, `list_devices_outside_target`, `get_compliance_summary`, `get_unknown_lifecycle_items`. | F1, F2 |
| F4 | Readiness & Prerequisites | `readiness-prerequisites` | `ReadinessEvaluation` controller; prerequisite rule engine; transitions `outside_target → ready_for_uplift / blocked`. MCP tools: `get_readiness_summary`, `explain_blockers`. | F2, F3 |
| F5 | Uplift Planning & Waves | `uplift-planning-waves` | `UpliftPlan` (dry-run only in v1); `UpliftWave` with approval gates; `Exception` entity; transitions `ready_for_uplift → uplift_planned → approval_pending → approved`. MCP tools: `create_uplift_wave_draft`, `create_exception_review_draft`, and the four reporting tools. | F3, F4 |
| F6 | MVP Vertical Slice Validation | `mvp-vertical-slice-cisco-isr1121` | Reference end-to-end proof for Cisco ISR1121: all MVP acceptance criteria from `gard-speckit-start/specs/04-mvp-scope.md` checked green. Integration tests, sample data, runbook. Not new product code. | F1–F5 |
| F7 | NetBox Integration (read-only, ecosystem-aware) | `netbox-integration-read` | First-class NetBox identity reference per ADR-0001. Read-only in v1: GARD pulls device identity/inventory from NetBox via the standard NetBox REST API and reconciles it with its own `Device` records. Acknowledges that NetBox is typically fed by **NetBox Discovery → NetBox Diode** in modern deployments — GARD is a downstream consumer of NetBox-as-source-of-truth, **not** a Diode client (Diode is a write-into-NetBox path). Includes positioning vs. **NetBox Assurance**: Assurance handles inventory/config drift, GARD handles firmware/lifecycle drift; they are complementary on the same source-of-truth. Write-back to NetBox deferred to v2. Optional Diode-SDK adapter for sites where Diode is the only data plane is a post-v1 follow-up. | F1 |

## Out of v1 scope

Each becomes its own feature when prioritized:

- **TR-069 / TR-369 adapter execution** — ADR-0005 puts ACS as southbound; v1 ships positioning + interface contract only, no execution.
- **NETCONF / CLI / NSO / Ansible / Nornir execution adapters** — same pattern as TR-069.
- **Full CVE / NVD / CPE matching automation** — v1 has manual / imported vulnerability intelligence only.
- **Native discovery** — v1 is CSV-fed.
- **Full SEGL certificate integration** — v1 has generic `LifecycleEvidence` only.
- **UI dashboards** — v1 is API + MCP + minimal admin surfaces only.
- **Closed-loop continuous reconciliation** — v1 is manually triggered evaluation.
- **NetBox write-back** — read-only in v1 (F7); write-back is a later feature.

## ADRs the roadmap will add

These are the binding decisions each feature is expected to capture as ADRs
during its `/speckit-plan` phase. Numbering continues from the existing
`ADR-0001` … `ADR-0005`:

- **ADR-0006 Language / runtime** (during F1)
- **ADR-0007 Database choice and migration tool** (during F1)
- **ADR-0008 Auth & RBAC model** (during F1)
- **ADR-0009 Audit & evidence storage strategy** (during F1)
- **ADR-0010 Normalization rules format & resolution order** (during F1)
- **ADR-0011 Catalog YAML schema & precedence** (during F2)
- **ADR-0012 Drift taxonomy formalization** (during F3)
- **ADR-0013 Prerequisite rule grammar** (during F4)
- **ADR-0014 Plan vs wave lifecycle and approval data model** (during F5)
- **ADR-0015 NetBox integration boundary & sync model** (during F7)
- **ADR-0016 GARD's place in the NetBox + Diode + Assurance ecosystem** (during F7) — formalizes the layering: NetBox owns identity, Discovery+Diode populate it, Assurance polices inventory/config drift, GARD polices firmware/lifecycle drift. Captures why GARD reads NetBox via REST (not Diode gRPC) in v1 and the conditions under which a Diode-SDK adapter would be added later

This list is non-binding for the roadmap itself; each `/speckit-plan` may
add, remove, or rename ADRs.

## How this roadmap is used

- The **active feature** is whichever feature has an open `specs/NNN-...`
  directory with `spec.md`/`plan.md`/`tasks.md` and a matching feature
  branch.
- A feature is **done** when its plan's Constitution Check passes, its
  tasks are all complete, and its PR is merged to `main`.
- Update this file in the same PR that finishes a feature: tick it off,
  add follow-up items discovered, and adjust the dependency graph if
  reality diverged.

## Current status

| Feature | Branch | Spec | Plan | Tasks | Implementation | Status |
|---|---|---|---|---|---|---|
| F1 device-import-normalize | `001-device-import-normalize` | drafted | — | — | — | Spec drafted (this PR series) |
| F2 firmware-catalog | — | — | — | — | — | Not started |
| F3 compliance-evaluation | — | — | — | — | — | Not started |
| F4 readiness-prerequisites | — | — | — | — | — | Not started |
| F5 uplift-planning-waves | — | — | — | — | — | Not started |
| F6 mvp-vertical-slice-cisco-isr1121 | — | — | — | — | — | Not started |
| F7 netbox-integration-read | — | — | — | — | — | Not started |
