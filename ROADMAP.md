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

| # | Feature | Slug | Status | Delivers | Depends on |
|---|---|---|---|---|---|
| F1 | Device Import & Normalize | `device-import-normalize` | **shipped** (`main`) | CSV import endpoint; `Device` + `DeviceObservation`; normalization rule engine (lifecycle-as-code); import summary + error report; transitions `imported → classified`. **Carries the platform-foundation work** (runtime/lang ADR, Postgres + migrations, auth + RBAC scaffolding, audit pipeline with `correlation_id`, `LifecycleEvidence` schema + emit helper, structured logging, REST + MCP skeletons, Docker Compose dev env, CI). First MCP tools: `list_devices`, `get_device_lifecycle_status` *(MCP transport deferred — see ADR-0013)*. | — |
| F2 | Firmware Catalog | `firmware-catalog` | **shipped** (PR #2) — REST complete, MCP deferred to F003 | `FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule`; YAML loader (lifecycle-as-code) + reload pipeline with Merkle-style chain-of-custody evidence; per-device firmware-compliance endpoint (`target_defined`/`compliant`/`outside_target`/`unknown`); Dijkstra upgrade-path API; SHA-256 verified blob upload/download with on-the-fly tamper detection on read. MCP tools `get_target_firmware`/`get_upgrade_path`/`list_*` — **deferred to F003** per ADR-0013 (REST surface delivers equivalent facts). | F1 |
| F3 | Compliance & Drift Evaluation | `compliance-drift-evaluation` | **shipped** (PR #3) — REST complete, MCP delegates ready, transport deferred to F008 | `ComplianceEvaluation` controller; 7-type drift taxonomy with explicit precedence (catalog > rule > package > target > discovery > evidence > exception, ADR-0014); idempotent append-only evaluation storage; typed `RecommendedAction` vocabulary with RBAC-aware `requires`; four REST endpoints (`/compliance/summary`, `/compliance/devices`, `/devices/{id}/compliance`, `/compliance/evaluate` with 5,000-device cap); reload-sync hook piggybacking on F2's bounded re-eval. MCP tools `count_devices_outside_target`, `list_devices_outside_target`, `get_compliance_summary`, `get_unknown_lifecycle_items` ship as delegates; transport deferred per ADR-0013. | F1, F2 |
| F4 | Readiness & Prerequisites | `readiness-prerequisites` | **shipped** (PR #4) — REST complete, MCP delegates ready, transport deferred to F008. `ReadinessEvaluation` controller; 11-kind blocker taxonomy (9 F2 prereq kinds + 2 synthetic `missing_upgrade_path` / `missing_observation_field`); R-1 severity+predicate-kind precedence locked in ADR-0015 (hardware > firmware-chain > licence > operational > synthetic); idempotent append-only storage; four REST endpoints (`/readiness/summary`, `/readiness/devices`, `/devices/{id}/readiness`, `/readiness/evaluate`); R-8 stale F3 input → 409 `READINESS_INPUT_STALE`; reload-sync extends F3's hook with set3 (prereq-rule-touched devices). MCP tools `get_readiness_summary`, `list_blocked_devices`, `explain_blockers`, `get_ready_for_uplift_devices` ship as delegates; transport deferred per ADR-0013. | F2, F3 |
| F5 | Uplift Planning & Waves | `uplift-planning-waves` | **shipped** (PR #5) — dry-run only; ADR-0016 | `UpliftPlan` (dry-run only in v1); `UpliftWave` with approval gates; `Exception` entity; transitions `ready_for_uplift → uplift_planned → approval_pending → approved`. MCP tools: `create_uplift_wave_draft`, `create_exception_review_draft`, and the four reporting tools. | F3, F4 |
| F6 | MVP Vertical Slice Validation | `mvp-vertical-slice-cisco-isr1121` | **shipped** (PR #6) | Reference end-to-end proof for Cisco ISR1121: all MVP acceptance criteria from `gard-speckit-start/specs/04-mvp-scope.md` checked green. Integration tests, sample data, runbook. Not new product code. | F1–F5 |
| F7 | NetBox Integration (read-only, ecosystem-aware) | `netbox-integration-read` | **shipped** (PR #7) | First-class NetBox identity reference per ADR-0001/0017/0018. Read-only: GARD pulls DCIM devices from NetBox REST, reconciles `Device` rows, populates tags for `tagged_with`, optional dev stack on port **18888** (`gard-f7-netbox`). MCP delegate `get_netbox_sync_summary`; transport deferred to F8. | F1 |
| F8 | Native MCP Transport | `mcp-transport` | **shipped** (`008-mcp-transport`, PR #8) | Live Streamable HTTP MCP server at `/mcp` with shared JWT/RBAC/audit. Registers all **22** tools from F1–F7 contracts; implements missing F1/F2 delegates. Closes MVP criterion #8 and ADR-0013 transport deferral (ADR-0019). | F1–F7 |
| F9 | NetBox Device Type Bootstrap | `netbox-devicetype-bootstrap` | **shipped** (`009-netbox-devicetype-bootstrap`, ADR-0020) | Curated import from community device type library for GARD-supported models only (pinned upstream manifest). Replaces hand-rolled dev seed types; prerequisite for NetBox write-back. | F7 |
| F10 | NetBox Lifecycle Write-Back | `netbox-writeback` | **shipped** (`010-netbox-writeback`, ADR-0021) | Post-sync push of GARD lifecycle metadata (custom fields + tags) to all NetBox-linked devices in sync batch. Conflict-safe, manifest-driven. | F7, F9, F3, F4 |

## Out of v1 scope

Each becomes its own feature when prioritized:

- **TR-069 / TR-369 adapter execution** — ADR-0005 puts ACS as southbound; v1 ships positioning + interface contract only, no execution.
- **NETCONF / CLI / NSO / Ansible / Nornir execution adapters** — same pattern as TR-069.
- **Full CVE / NVD / CPE matching automation** — v1 has manual / imported vulnerability intelligence only.
- **Native discovery** — v1 is CSV-fed.
- **Full SEGL certificate integration** — v1 has generic `LifecycleEvidence` only.
- **UI dashboards** — v1 is API + MCP + minimal admin surfaces only.
- **Closed-loop continuous reconciliation** — v1 is manually triggered evaluation.
- **NetBox write-back** — F10 shipped (`010-netbox-writeback`, ADR-0021); post-sync lifecycle mirror via custom fields + tags.

## ADRs the roadmap will add

These are the binding decisions each feature is expected to capture as ADRs
during its `/speckit-plan` phase. Numbering continues from the existing
`ADR-0001` … `ADR-0005`:

- **ADR-0006 Language / runtime** (during F1)
- **ADR-0007 Database choice and migration tool** (during F1)
- **ADR-0008 Auth & RBAC model** (during F1)
- **ADR-0009 Audit & evidence storage strategy** (during F1)
- **ADR-0010 Normalization rules format & resolution order** (during F1)
- **ADR-0011 Catalog YAML schema & precedence** (during F2) — *shipped*
- **ADR-0012 `LifecycleState.unknown` as first-class state** (during F2) — *shipped, reassigned from "drift taxonomy"; the drift-taxonomy decision moves to F3*
- **ADR-0013 MCP firmware tools deferred to F003** (during F2) — *shipped, reassigned from "prerequisite rule grammar"; the prereq-grammar decision moves to F4*
- **ADR-0014 Drift taxonomy formalization** (during F3) — *renumbered from planned ADR-0012*
- **ADR-0015 Readiness verdict precedence + biconditional rules** (during F4) — *shipped; supersedes the placeholder "prerequisite rule grammar" — the prereq grammar itself was already defined by F2's `firmware_prerequisite_rules` table, so F4's binding decision became blocker precedence + state-transition biconditionals instead*
- **ADR-0016 Wave state machine and separation-of-duties** (F5) — closed wave + exception state machines, three-layer SoD, lazy exception expiry, idempotency-key contract
- **ADR-0017 NetBox integration boundary & sync model** (during F7) — *renumbered from planned ADR-0015*
- **ADR-0018 GARD's place in the NetBox + Diode + Assurance ecosystem** (during F7) — *renumbered from planned ADR-0016*. Formalizes the layering: NetBox owns identity, Discovery+Diode populate it, Assurance polices inventory/config drift, GARD polices firmware/lifecycle drift. Captures why GARD reads NetBox via REST (not Diode gRPC) in v1 and the conditions under which a Diode-SDK adapter would be added later
- **ADR-0019 MCP transport binding** (during F8) — Streamable HTTP mount, shared auth, tool registry, deny-list; closes ADR-0013 deferral

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

## Per-feature README convention

Every feature directory under `specs/` MUST contain a `README.md` next to
its `spec.md`. The per-feature README is the **navigation + changelog**
for that feature — it complements but does not replace the formal
artifacts. Required sections:

1. **TL;DR** — what the feature delivers, in 2 sentences
2. **Status** — table of artifacts (spec, plan, research, data-model,
   contracts, quickstart, tasks, implementation) with the latest update
   date and a one-line summary
3. **Timeline** — dated bullets logging significant decisions and events
   (spec drafted, clarifications run, plan added, ADRs reserved, tasks
   generated, PRs opened/merged, scope changes)
4. **Scope guards** — what IS in this feature, what is NOT (with the
   feature that picks up each cut item), and any cross-cutting changes
   it caused elsewhere in the project
5. **ADRs born in this feature** — table of ADRs proposed or accepted
   during the feature, with status and source-decision reference
6. **Pull requests** — links to all PRs that touched this feature, in
   chronological order
7. **How to run / verify** — one paragraph linking to `quickstart.md`
8. **Related references** — links to the constitution, roadmap, and
   any seed material the feature was built on

The `/speckit-specify` flow scaffolds a stub README; subsequent
`/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, and
`/speckit-clarify` runs MUST append a Timeline bullet and update the
Status table for the artifact they touched. The first canonical example
is [`specs/001-device-import-normalize/README.md`](./specs/001-device-import-normalize/README.md).

## Current status

| Feature | Branch | Spec | Plan | Tasks | Implementation | Status |
|---|---|---|---|---|---|---|
| F1 device-import-normalize | `001-device-import-normalize` | drafted | — | — | — | Spec drafted (this PR series) |
| F2 firmware-catalog | — | — | — | — | — | Not started |
| F3 compliance-evaluation | — | — | — | — | — | Not started |
| F4 readiness-prerequisites | — | — | — | — | — | Not started |
| F5 uplift-planning-waves | `005-uplift-planning-waves` | done | done | done | shipped (PR #5) | Merged to main |
| F6 mvp-vertical-slice-cisco-isr1121 | `006-mvp-vertical-slice-cisco-isr1121` | done | done | shipped (PR #6) | — | Merged |
| F7 netbox-integration-read | `007-netbox-integration-read` | done | done | in progress | — | 7a–7d landing |
