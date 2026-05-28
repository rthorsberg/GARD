# F1 — Device Import & Normalize

> **What this feature delivers**: a CSP operator uploads a device-inventory CSV
> and immediately sees normalized, deduplicated `Device` records via REST and
> MCP, with full audit + evidence and a reviewable manual-review backlog. Also
> lays the platform foundation (auth, RBAC, audit, evidence, REST + MCP
> skeletons, Docker Compose dev env) that every later feature builds on.

This README is the **navigation + changelog** for F1. It complements — does
not replace — the formal artifacts in this directory. If you're hunting for
"what is the contract", read `contracts/`. If you're hunting for "why did we
choose Postgres", read `research.md`. If you want a guided tour of the work,
read on.

## Status

| Artifact | Path | Latest update | One-line summary |
|---|---|---|---|
| Spec | [`spec.md`](./spec.md) | 2026-05-27 | 3 user stories (P1 import, P2 review, P2 MCP), 23 FRs, 8 SCs, 0 NEEDS CLARIFICATION |
| Quality checklist | [`checklists/requirements.md`](./checklists/requirements.md) | 2026-05-27 | All 16 items pass; one borderline FR-006 sync/async threshold accepted |
| Plan | [`plan.md`](./plan.md) | 2026-05-27 | Python 3.12 + FastAPI + Postgres 16 + MCP SDK; Constitution Check PASS pre + post-design |
| Research | [`research.md`](./research.md) | 2026-05-27 | 10 binding decisions D1–D10 feeding ADRs 0006–0010 |
| Data model | [`data-model.md`](./data-model.md) | 2026-05-27 | 8 entities, append-only DB roles, F1 state transitions, cross-cut invariants |
| REST contract | [`contracts/rest-openapi.yaml`](./contracts/rest-openapi.yaml) | 2026-05-27 | Full OpenAPI 3.1 surface for imports, devices, observations, normalization, audit, evidence |
| MCP contract | [`contracts/mcp-tools.yaml`](./contracts/mcp-tools.yaml) | 2026-05-27 | `list_devices` + `get_device_lifecycle_status` with bounded schemas + disallowed list |
| CSV schema | [`contracts/csv-schema.yaml`](./contracts/csv-schema.yaml) | 2026-05-27 | Versioned CSV ingest schema + row validations + error vocabulary |
| Rule schema | [`contracts/normalization-rule.schema.yaml`](./contracts/normalization-rule.schema.yaml) | 2026-05-27 | JSON Schema 2020-12 for catalog + DB override rules |
| Quickstart | [`quickstart.md`](./quickstart.md) | 2026-05-27 | 10-step operator walkthrough mapped to every SC-00x |
| Tasks | [`tasks.md`](./tasks.md) | 2026-05-28 | 130 tasks across 6 phases; MVP at end of Phase 3 |
| **Implementation** | `gard/`, `gard-catalog/`, `tests/`, `adr/`, `deploy/` | — | **Not started yet** — kicks off on `/speckit-implement` |

## Timeline

A dated log of significant decisions and events for this feature. Append a
new bullet whenever the feature meaningfully changes.

- **2026-05-27** — Feature branch `001-device-import-normalize` created off
  `main`. Spec drafted from the seed material in `gard-speckit-start/`,
  validated against the quality checklist on first pass with no clarification
  questions queued.
- **2026-05-27** — Plan + research + data model + contracts + quickstart
  authored in one session. Constitution Check **PASS** both pre-design and
  post-design. Ten binding decisions (D1–D10) recorded in `research.md`,
  mapped to ADRs 0006–0010 to be authored during Phase 1 of implementation.
- **2026-05-28** — `tasks.md` generated: 130 dependency-ordered tasks across
  6 phases, MVP checkpoint at end of Phase 3.
- **2026-05-28** — Draft PR [#1] opened against `main` for human review of
  the full specification bundle before any code lands.
- **2026-05-28** — Researched NetBox Diode, NetBox Discovery / Orb-Agent, and
  NetBox Assurance to confirm GARD's positioning. **No F1 changes required**
  — the discovery validates F1's existing decisions (CSV ingest in v1, NetBox
  deferred to F7). Updated `ROADMAP.md` (F7 rescoped, ADR-0016 reserved) and
  `README.md` (positioning sentence) on this same branch.
- **2026-05-28** — Added this per-feature `README.md` and the project-wide
  per-feature-README convention to `ROADMAP.md`.

## Scope guards

### What IS in F1

- CSV ingest (sync ≤ 10k rows; async > 10k via worker)
- Canonical `Device` upsert with serial-first / hostname+site-fallback identity
- Normalization rule engine: 3-tier resolution (manual mapping → DB override →
  YAML catalog), specificity + priority + deterministic conflict handling
- Manual-mapping review loop without re-uploading CSV
- Lifecycle states `imported` and `classified` (later features extend the rest)
- Auth (OIDC + signed JWT API tokens), RBAC catalog, audit log with checksum
  chain, `LifecycleEvidence` emission
- REST surface for imports, devices, observations, normalization, audit, evidence
- MCP server with `list_devices` and `get_device_lifecycle_status`
- Docker Compose dev environment + CI

### What is NOT in F1 (and which feature picks it up)

| Cut item | Picked up by |
|---|---|
| `FirmwareTarget`, `FirmwarePackage`, `UpgradePath`, `PrerequisiteRule` | F2 firmware-catalog |
| Compliance / drift evaluation | F3 compliance-evaluation |
| Readiness / blocker engine | F4 readiness-prerequisites |
| `UpliftPlan`, `UpliftWave`, approval gates | F5 uplift-planning-waves |
| Reference end-to-end vertical-slice test (Cisco ISR1121) | F6 mvp-vertical-slice-cisco-isr1121 |
| NetBox identity reference (read-only) | F7 netbox-integration-read |
| TR-069 / NETCONF / CLI / NSO adapter execution | Out of v1 |
| Native discovery, full CVE/NVD automation, UI dashboards, NetBox write-back | Out of v1 |

### What changed during F1's life that you should know about

- **Roadmap F7 rescoped** to "NetBox Integration (read-only, ecosystem-aware)"
  after research into NetBox Diode and NetBox Assurance. F1 unaffected.

## ADRs born in this feature

These ADRs are *reserved* by F1's research; they are authored as Phase 1
implementation tasks (T009–T013 in `tasks.md`) so the rationale ships in the
same PR series as the code that implements it.

| ADR | Subject | Status | Source |
|---|---|---|---|
| ADR-0006 | Language & runtime (Python 3.12) | Reserved (T009) | `research.md` D1 |
| ADR-0007 | Database & migrations (PostgreSQL 16 + SQLAlchemy 2 + Alembic) | Reserved (T010) | `research.md` D2 |
| ADR-0008 | Auth & RBAC (OIDC + signed JWT, single FastAPI dependency) | Reserved (T011) | `research.md` D3 |
| ADR-0009 | Audit & evidence storage (append-only DB roles + daily checksum chain) | Reserved (T012) | `research.md` D4 |
| ADR-0010 | Normalization rules format (YAML + DB override, 3-tier resolution) | Reserved (T013) | `research.md` D5 |

ADRs 0001–0005 are the project-level seed ADRs, kept in
`gard-speckit-start/adr/` as historical input.

## Pull requests

| PR | Branch | What it contains | Status |
|---|---|---|---|
| [#1](https://github.com/rthorsberg/GARD/pull/1) | `001-device-import-normalize` | Specification bundle (this directory) — no code | Draft, awaiting review |

When implementation starts, expect this list to grow with one PR per phase
(or per logical chunk of phase) — Phase 1 Setup PR, Phase 2 Foundational PR,
US1 PR, US2 PR, US3 PR, Polish PR — all targeting `main` from this same
branch or short-lived child branches.

## How to run / verify F1

When implementation has landed:

```bash
cd deploy
cp .env.example .env   # set OIDC + DB + JWT signing
docker compose up -d
```

Then walk [`quickstart.md`](./quickstart.md) end-to-end. Step 10 of the
quickstart maps each acceptance check to its corresponding success criterion
(SC-001 through SC-008) so you can spot-verify the constitutional invariants
without reading any source.

While F1 is still pre-implementation, the artifacts in this directory are
the contract — review them in the order: `spec.md` → `plan.md` →
`research.md` → `contracts/` → `quickstart.md` → `tasks.md`.

## Related references

- [`../../.specify/memory/constitution.md`](../../.specify/memory/constitution.md) — the seven principles every change is checked against
- [`../../ROADMAP.md`](../../ROADMAP.md) — where F1 sits in the v1 sequence
- [`../../gard-speckit-start/`](../../gard-speckit-start/) — the seed PRD, domain model, lifecycle state machine, and ADRs that F1 is built on
