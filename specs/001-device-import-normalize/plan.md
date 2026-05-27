# Implementation Plan: Device Import & Normalize

**Branch**: `001-device-import-normalize` | **Date**: 2026-05-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-device-import-normalize/spec.md`

## Summary

Deliver the GARD foundation slice: a CSP operator uploads a device-inventory
CSV via an authenticated REST endpoint; GARD records every row as an
immutable `DeviceObservation`, normalizes raw vendor/model/platform values
to canonical entities via a versioned rule engine, upserts canonical
`Device` records, and exposes both the result and the lifecycle state via
REST and a minimal MCP server (`list_devices`,
`get_device_lifecycle_status`). Because F1 is the first feature on the
roadmap, it also lays the binding platform foundation: PostgreSQL +
Alembic, OIDC + API-token auth + RBAC middleware, append-only audit log
with checksum chain, `LifecycleEvidence` emission, structured logging
with `correlation_id`, REST (FastAPI) + MCP (official Python SDK,
Streamable HTTP), and Docker Compose dev/CI environment.

## Technical Context

**Language/Version**: Python 3.12 *(ADR-0006, see research.md)*
**Primary Dependencies**: FastAPI ≥ 0.115, Pydantic v2, SQLAlchemy 2.x +
Alembic, `mcp` (official Python SDK) on Streamable HTTP transport,
`authlib` (OIDC), `python-jose` (JWT), `structlog`, `httpx` (test client),
`pytest` + `pytest-asyncio`
**Storage**: PostgreSQL 16 + JSONB for raw payloads and evidence;
Alembic for migrations *(ADR-0007)*
**Testing**: pytest with three tiers — `tests/contract/`,
`tests/integration/`, `tests/unit/` — per the constitution's
contract-and-integration-first posture
**Target Platform**: Linux server; deployed as one Docker image with an
API process and a worker process; PostgreSQL alongside
**Project Type**: Single backend service (REST + MCP from one codebase)
**Performance Goals**: 10,000-row CSV ingest summary returned within 30 s
(SC-001); MCP `list_devices` answer in < 2 s at 50,000 devices (SC-005)
**Constraints**: Append-only audit log enforced at DB role level; no raw
SQL/shell/file-system from MCP (Constitution VI); explainable response
envelope on every classification (Constitution V); zero silent defaults
(Constitution III)
**Scale/Scope**: v1 targets a single CSP estate up to ~50,000 devices,
single tenant, single deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0.

| Principle | Status | How this plan complies |
|---|---|---|
| I. Governance Before Execution | ✅ | F1 has no device-mutation surface — ingest, normalize, list, and explain only. Every state-mutating *administrative* action (rule add/update/disable, manual mapping, re-evaluate, import override) is RBAC-gated and audited. No approval gate is needed in F1 because no production device state is changed. |
| II. Desired ↔ Actual State Separation | ✅ | `Device` is the canonical slow-changing record; `DeviceObservation` is immutable time-bound actual state. `lifecycle_state` on `Device` is derived from observations and never written by adapters. `FirmwareTarget` (desired state) is explicitly out of scope (F2). |
| III. Unknown Is a First-Class State | ✅ | Confidence enum includes `manual_review_required`; FR-008/010 forbid silent defaults; SC-003/SC-004 measure that every row is either accepted or has a per-row reason, and every unknown is queryable. |
| IV. Lifecycle-as-Code | ✅ | Normalization rules ship as versioned YAML in `gard-catalog/normalization/`, loaded at boot, with a DB-backed override layer for hot edits; ADR-0010 fixes the deterministic resolution order. Rule API writes are exportable back to YAML. |
| V. Evidence, Audit & Explainability (NON-NEGOTIABLE) | ✅ | Every state-mutating action emits an `AuditEvent` (FR-017); every import + manual classification emits a `LifecycleEvidence` record (FR-018); audit table is append-only at the PostgreSQL role level with a daily checksum chain (ADR-0009); every classification response carries `{state, summary, facts, reasons, recommended_actions, confidence}` (FR-015). |
| VI. MCP Exposes Curated Tools, Not Raw Infrastructure | ✅ | MCP server uses the official Python SDK on Streamable HTTP, fronted by the same OIDC/RBAC middleware as REST. The only v1 tools are `list_devices` and `get_device_lifecycle_status`, both bounded and paginated; no SQL, shell, or filesystem tool is exposed. |
| VII. Integration Over Replacement | ✅ | F1 consumes CSV exports from existing discovery systems; NetBox is explicitly deferred to F7; no adapter execution code lands in F1. |

**Additional Constraints**: Security checks (secrets via env / mounted
secret-store abstraction, RBAC separating read/admin in F1's role
subset, package-integrity not relevant in F1, append-only audit) and
Quality (contract + integration mandatory) are met. Architecture
Boundaries: REST and MCP both call the same controllers; no
controller→adapter calls (no adapters in F1).

**Result**: **PASS, no exceptions required.** Complexity Tracking
section omitted.

### Post-design re-check (after Phase 1)

Re-evaluated after writing `data-model.md`, `contracts/`, and
`quickstart.md`:

- **Principle II** is *strengthened* — the data model enforces
  `DeviceObservation` immutability at the DB role level
  (`gard_writer_append_only`), and `Device.lifecycle_state` derivations
  are owned by controllers, not adapters.
- **Principle III** is enforced concretely by CSV schema row validations
  (`ROW_MISSING_IDENTITY`, `ROW_MISSING_VENDOR_AND_MODEL`) and by the
  resolution-order rule that never produces a default — only
  `manual_review_required`.
- **Principle IV** survives the DB-override layer because every override
  is exportable back to YAML (`exported_at` timestamp); the resolution
  order pins file rules below manual mappings only, not below db
  overrides as a category, keeping Git-as-source-of-truth intact.
- **Principle V** is mechanized via append-only DB roles + daily
  checksum chain (ADR-0009) and the `Envelope` schema in every public
  contract (REST + MCP).
- **Principle VI** is mechanized by the MCP server sharing the FastAPI
  auth dependency and emitting `mcp.tool.invoked` audit events from the
  same helper used by REST handlers.

**Result**: **PASS confirmed post-design.** No new violations
introduced.

## Project Structure

### Documentation (this feature)

```text
specs/001-device-import-normalize/
├── plan.md                # This file
├── research.md            # Phase 0 output — binding decisions
├── data-model.md          # Phase 1 output — entities, fields, transitions
├── contracts/             # Phase 1 output — REST, MCP, CSV, rule schemas
│   ├── rest-openapi.yaml
│   ├── mcp-tools.yaml
│   ├── csv-schema.yaml
│   └── normalization-rule.schema.yaml
├── quickstart.md          # Phase 1 output — operator quickstart
├── checklists/
│   └── requirements.md    # From /speckit-specify
└── tasks.md               # Phase 2 output — created by /speckit-tasks
```

### Source Code (repository root)

```text
gard/                              # The product code (single deployable)
├── api/                           # FastAPI routers + dependency-injection wiring
│   ├── routers/
│   │   ├── imports.py
│   │   ├── devices.py
│   │   ├── observations.py
│   │   ├── normalization.py
│   │   ├── audit.py
│   │   └── evidence.py
│   ├── middleware/                # auth, RBAC, correlation_id, audit emission
│   └── schemas/                   # Pydantic request/response models
├── mcp/                           # MCP server using official Python SDK
│   ├── server.py                  # transport + auth bridge
│   └── tools/
│       ├── list_devices.py
│       └── get_device_lifecycle_status.py
├── core/                          # Domain controllers (no I/O dependencies)
│   ├── import_controller.py
│   ├── normalization_controller.py
│   ├── device_controller.py
│   ├── audit.py                   # AuditEvent emit helper
│   └── evidence.py                # LifecycleEvidence emit helper
├── models/                        # SQLAlchemy ORM models
├── db/                            # session + migrations entry
│   └── migrations/                # Alembic
├── catalog/                       # Lifecycle-as-Code loaders
│   └── normalization_loader.py
├── settings.py                    # Pydantic-settings, env-driven config
├── logging.py                     # structlog config
└── worker.py                      # async import worker entrypoint

gard-catalog/                      # Lifecycle-as-Code seed catalog (Git-managed)
└── normalization/
    └── cisco.yaml                 # Initial rules for the Cisco reference family

tests/
├── contract/                      # REST + MCP + CSV + rule schema contracts
├── integration/                   # End-to-end import flow, MCP query, RBAC
└── unit/                          # Rule engine, identity resolution, audit chain

adr/                               # Project-level ADRs (0006+ ship in F1)
├── ADR-0006-language-and-runtime.md
├── ADR-0007-database-and-migrations.md
├── ADR-0008-auth-and-rbac.md
├── ADR-0009-audit-and-evidence-storage.md
└── ADR-0010-normalization-rules-format.md

deploy/
├── docker-compose.yml             # API + worker + Postgres for dev
├── Dockerfile
└── .env.example
```

**Structure Decision**: Single backend service (Python monorepo, no
frontend in v1). REST (`gard.api`), MCP (`gard.mcp`), and a worker
(`gard.worker`) all share the `gard.core` controllers and `gard.models`
ORM layer — eliminating two code paths to the same domain logic and
satisfying Constitution VI ("MCP flows through the same RBAC and audit
pipeline as REST"). ADRs live at the project root (`adr/`) starting from
0006; the seed ADRs 0001–0005 stay in `gard-speckit-start/adr/` as
historical input.
