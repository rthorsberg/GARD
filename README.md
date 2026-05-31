# GARD

**Service Lifecycle Guardrails** — an MCP-native firmware/software lifecycle
governance platform for Communication Service Provider (CSP) network
infrastructure.

> GARD gives a CSP control over the firmware/software lifecycle of its network
> estate — from discovered actual state to approved target state, safe uplift
> planning, and lifecycle evidence.

## What we're building

GARD is the **lifecycle control plane** for CSP networks. It answers, for every
device in the estate:

1. What is it running today?
2. What should it be running?
3. What's the drift, the risk, and is it ready to uplift?
4. What's the exact plan to get it compliant?
5. Who approved it, and what evidence proves the result?

GARD is **not** a firmware-push script. Traditional tooling asks *"How do I push
this image to this device?"* — GARD asks *"Should this device be upgraded, to
what, through which path, under which prerequisites, with what risk, approved by
whom, executed by which adapter, validated how, and evidenced where?"*



## Why we're building

GARD is a prototype for seeing how far I can get with Github speckit and a bunch of cursor tokens,  and a pretty good idea on what I want to archieve.

I want to build a framwork for how to analyze and uplift new onboarded, and existing installbase devices to the target firmware versions. 

## Product boundary

- **NetBox** (or equivalent) remains the source of infrastructure identity.
- **GARD** owns lifecycle policy, target state, drift, risk, readiness,
planning, approval and evidence.
- **TR-069 / TR-369 / NETCONF / CLI / NSO / Ansible / netmiko / vendor APIs** are  
southbound execution adapters — GARD never replaces them.
- **MCP** exposes curated, audited lifecycle tools to approved AI agents — never
raw SQL or shell.

GARD is **complementary** to **NetBox Assurance**, not a competitor: Assurance
keeps NetBox documentation honest (inventory and configuration drift); GARD
keeps the firmware/software lifecycle governed (target drift, readiness, uplift
planning, evidence). Both sit on the same NetBox source-of-truth, which itself
is typically populated by NetBox Discovery → NetBox Diode in modern
deployments.

See `[gard-speckit-start/adr/](gard-speckit-start/adr/)` for the binding
architectural decisions.

## Repository layout

```text
.
├── .specify/
│   ├── memory/constitution.md      # GARD Constitution (v1.0.0, ratified)
│   ├── templates/                  # Spec Kit templates (spec, plan, tasks, ...)
│   ├── extensions/                 # Spec Kit Git extension (hooks)
│   └── workflows/                  # Spec Kit workflow registry
├── .cursor/
│   ├── rules/specify-rules.mdc     # Always-on rule pointing the agent at the plan
│   └── skills/                     # Spec Kit skills (specify, plan, tasks, ...)
├── gard-speckit-start/             # Seed material for the Spec Kit flow
│   ├── README.md                   # Recommended reading order
│   ├── context/                    # Product brief, domain assumptions
│   ├── specs/                      # PRD, domain model, lifecycle, architecture,
│   │                               #   MVP scope, MCP, security, API surface
│   ├── adr/                        # ADR-0001 … ADR-0005
│   └── examples/                   # Sample CSV, target/upgrade-path YAML, MCP tools
└── README.md                       # You are here
```

## Constitution (the binding rules)

Seven principles govern every change. Full text:
`[.specify/memory/constitution.md](.specify/memory/constitution.md)`.

1. **Governance Before Execution** — no autonomous v1; approval gates everywhere.
2. **Desired State and Actual State Are Separate** — drift/risk/readiness are
  derived, never stored as truth.
3. **Unknown Is a First-Class Lifecycle State** — no silent defaults, no hidden
  rows.
4. **Lifecycle-as-Code** — catalogues version-controlled with declared schemas.
5. **Evidence, Audit & Explainability (NON-NEGOTIABLE)** — append-only audit +
  `LifecycleEvidence` + cited classifications.
6. **MCP Exposes Curated Tools, Not Raw Infrastructure** — same RBAC + audit as
  the REST surface.
7. **Integration Over Replacement** — NetBox = identity; TR-069/NETCONF/NSO =
  adapters.

## How we work

This repository uses [Spec Kit](https://github.com/github/spec-kit) for
specification-driven development. The workflow per feature is:

```text
/speckit-specify    →  draft the feature spec
/speckit-clarify    →  resolve open questions (when needed)
/speckit-plan       →  produce the implementation plan + Constitution Check
/speckit-tasks      →  generate the dependency-ordered task list
/speckit-implement  →  execute tasks
```

The **Constitution Check** gate in the plan template is the primary enforcement
point: any plan that violates a principle must justify it in the plan's
Complexity Tracking section and be approved before implementation.

## Status

- ✅ Constitution v1.0.0 ratified (2026-05-27)
- ✅ Spec Kit + Git extension installed
- ✅ GARD seed material imported (`gard-speckit-start/`)
- ✅ **F1 — Device Import & Normalize** shipped on `main` (CSV import,
  normalization rule engine, audit/evidence pipeline, RBAC, JWT auth,
  REST API, Docker Compose dev env, CI)
- ✅ **F2 — Firmware Catalog** shipped on `002-firmware-catalog` (PR #2)
  REST-complete: catalog YAML loader, per-device firmware-compliance
  endpoint, upgrade-path Dijkstra API, prerequisite rules, blob
  upload/download with verified SHA-256 round-trip, Merkle-style
  chain-of-custody evidence per reload. MCP tools for F2 deferred to
  follow-up feature `003-mcp-firmware-tools` (ADR-0013).
- ✅ **F3 — Compliance & Drift Evaluation** shipped on
  `003-compliance-drift-evaluation` (PR #3). 7-type drift taxonomy
  (catalog / rule / package / target / discovery / evidence /
  exception) with explicit precedence ordering (ADR-0014),
  append-only `compliance_evaluations` storage with idempotent
  evaluator, typed `RecommendedAction` vocabulary, four REST
  endpoints (`/compliance/summary`, `/compliance/devices`,
  `/devices/{id}/compliance`, `/compliance/evaluate`), four MCP
  tool delegates (transport still deferred), and a reload-sync hook
  that piggybacks on F2's bounded re-eval.
- ✅ **F4 — Readiness & Prerequisites** shipped on
  `004-readiness-prerequisites` (PR #4). 3-state readiness taxonomy
  (`ready_for_uplift` / `blocked` / `not_applicable`) with closed
  predicate-kind enum spanning F2's 9 prerequisite kinds plus 2
  synthetic kinds (`missing_upgrade_path`, `missing_observation_field`).
  Verdict precedence + biconditional rules locked in ADR-0015.
  Append-only `readiness_evaluations` storage with R-5 idempotency,
  four REST endpoints (`/readiness/summary`, `/readiness/devices`,
  `/devices/{id}/readiness`, `/readiness/evaluate`), four MCP tool
  delegates, and a reload-sync extension that adds prereq-rule-touched
  devices to F3's existing affected set.
- ✅ **F5 — Uplift Planning & Waves** shipped on `main` (PR #5).
  Turns F4's `ready_for_uplift` pool into reviewable change packets:
  `UpliftPlan` + `UpliftWave` with separation-of-duties approval
  (ADR-0016), `Exception` escape hatch for blocked devices, lazy
  exception expiry wired into F4 evaluate, uplift REST surface, and
  six read-shaped MCP delegates.
- ✅ **F6 — MVP Vertical Slice Validation** shipped on `main` (PR #6).
  Cisco ISR1121 end-to-end proof: 12 integration tests, ISR1121 catalog,
  `seed-isr1121.sh`.
- 🚧 **F7 — NetBox Integration (read-only)** on
  `007-netbox-integration-read`. Pull device identity from NetBox REST;
  isolated dev stack on port **18888** (`gard-f7-netbox` Docker project).
- ⏭️ **Next after F7**: execution adapters / MCP transport (post-v1).

## Quickstart

The local stack is a 3-container Docker Compose: Postgres, the GARD
API, and a one-shot Alembic migration runner.

```bash
make up-build          # build images + start stack
make seed              # mint a dev JWT + import 5 sample devices +
                       # reload the firmware catalog + walk per-device
                       # firmware compliance
open http://127.0.0.1:8080/docs    # interactive Swagger UI
```

After `make seed` you should see:

```
==> Firmware compliance snapshot (F2)
    2 firmware target(s) loaded:
      - cisco-iosxr-edge       platform=iosxr   target_version=7.8.1
      - juniper-junos-core     platform=junos   target_version=23.2R1

==> Per-device firmware compliance
    r5.bergen     compliant      target_ver=23.2R1     observed=23.2R1
    r4.bergen     compliant      target_ver=7.8.1      observed=7.8.1
    r3.oslo       classified     target_ver=-          observed=23.10.R3
    r2.oslo       outside_target target_ver=23.2R1     observed=22.4R3-S2
    r1.oslo       outside_target target_ver=7.8.1      observed=7.5.2

==> F3: estate-wide drift summary
    total_evaluated=5 compliant=2 unknown=0
      - catalog_drift      1
      - package_drift      2
      - evidence_drift     2

==> F3: per-device drift classification
    r1.oslo   state=outside_target drift=package_drift  secondary=target_drift  actions=upgrade_path_query,upload_firmware_package
    r2.oslo   state=outside_target drift=package_drift  secondary=target_drift  actions=upgrade_path_query,upload_firmware_package
    r4.bergen state=compliant      drift=evidence_drift secondary=-             actions=request_observation_refresh
    r5.bergen state=compliant      drift=evidence_drift secondary=-             actions=request_observation_refresh
    r3.oslo   state=classified     drift=catalog_drift  secondary=-             actions=define_target

==> F4: estate-wide readiness summary
    total_outside_target=2 ready_for_uplift=0 blocked=2 not_applicable=3
    top_blocker_categories:
      - min_disk_mb                  2

==> F4: per-device readiness verdict
    r1.oslo        state=blocked            primary=min_disk_mb            rule=iosxr-minimum-disk
    r2.oslo        state=blocked            primary=missing_observation_field rule=iosxr-minimum-disk
    r3.oslo        state=not_applicable     primary=-                      rule=-
    r4.bergen      state=not_applicable     primary=-                      rule=-
    r5.bergen      state=not_applicable     primary=-                      rule=-

==> F5: estate-wide plan + wave summary
    plans_returned=1
      - seed-demo-plan       waves=0 archived=False
    waves_returned=0
```

The `r3.oslo` device shows `classified` + `catalog_drift` (no firmware
target matches its Nokia SR-OS platform) by design — operators get
to observe the `no_target_matched` reason in the compliance envelope
and a `define_target` recommended action.

The seed runs against 5 devices, but the same endpoints scale to
thousands; the summary endpoint is a single DISTINCT-ON aggregate
that returns in well under a second on the 5,000-device synthetic
target (see `specs/003-compliance-drift-evaluation/plan.md`).

Other useful targets:

| Target | What it does |
|---|---|
| `make reset` | Wipe Postgres + blob volumes, rebuild image, reseed |
| `make logs` | Tail the API container |
| `make token` | Mint a fresh dev JWT (printed to stdout) |
| `make test` | Run the local test suite against the running stack |
| `make lint` | `ruff format --check` + `ruff check` |

## North star

> No device left unknown. No firmware left unmanaged. No uplift without
> readiness.

