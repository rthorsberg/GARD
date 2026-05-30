# Implementation Plan: Firmware Catalog

**Branch**: `002-firmware-catalog` | **Date**: 2026-05-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-firmware-catalog/spec.md`

## Summary

Deliver the firmware-policy layer GARD has been building toward: an operator-authored, git-managed catalog of `FirmwareTarget` policies, `FirmwarePackage` artefacts (with optional checksum-verified blob storage), `UpgradePath` edges (shortest-path traversal), and `PrerequisiteRule` declarations (declarative grammar, evaluation deferred to F4). Building on F1, F2 introduces three new device lifecycle states (`target_defined`, `compliant`, `outside_target`) and a thin per-device compliance read (`GET /api/v1/devices/{id}/firmware-compliance`). F3 will layer drift taxonomy on top without changing this state machine.

The catalog's source of truth is YAML files under `gard-catalog/firmware/`; approval is the merged PR (no in-app workflow). The loader anchors every loaded row to a git commit SHA in the audit trail. MCP gains five read-only tools (`get_target_firmware`, `get_upgrade_path`, and three `list_*` tools). A new `BlobStore` protocol with a single concrete `LocalFsBlobStore` adds optional firmware-image upload + chunked SHA-256 verification, bounded by a 5 GiB cap. A new ADR-0011 records the catalog schema + git-precedence model.

## Technical Context

**Language/Version**: Python 3.12 *(continues ADR-0006)*
**Primary Dependencies**: FastAPI ≥ 0.115, Pydantic v2, SQLAlchemy 2.x + Alembic, `mcp` (official Python SDK on Streamable HTTP), `structlog`, `pyyaml`, `jsonschema` (2020-12 validator), `httpx` (tests), `pytest` + `pytest-asyncio`. **One new third-party dependency**: `networkx` (≥ 3.2) for the upgrade-path Dijkstra. No vendor SDKs; no S3 client.
**Storage**: PostgreSQL 16 (continues F1 schema): four new tables (`firmware_targets`, `firmware_packages`, `firmware_upgrade_paths`, `firmware_prerequisite_rules`) plus three new columns on `devices` (`ram_mb`, `disk_mb`, `licenses`) and an extension of the `lifecycle_state` enum with three new values. Plus one new audit-emit kind family `firmware_catalog.*`. Blob storage is filesystem-backed via `LocalFsBlobStore` rooted at `GARD_BLOB_ROOT`.
**Testing**: pytest, three tiers as in F1 — `tests/contract/` (REST + MCP + catalog YAML schemas), `tests/integration/` (load → resolve → read flow against live Postgres; blob upload round-trip), `tests/unit/` (Dijkstra correctness on adversarial graphs, scope-selector evaluation, predicate-parser invariants).
**Target Platform**: Linux server; deployed as the single Docker image from F1. The compose stack gains one named volume `deploy_gard-blobs` mounted at `/var/lib/gard/blobs/`.
**Project Type**: Single backend service (additive to F1's `gard/` package — no new top-level packages).
**Performance Goals**: `GET /devices/{id}/firmware-compliance` p95 < 250 ms over 5,000 devices × 200 targets (SC-001); `GET /firmware/upgrade-paths` p95 < 50 ms over a 500-edge × 200-platform graph (SC-006); catalog reload of 1,000 mixed YAML files completes in < 10 s; blob upload sustains ≥ 100 MB/s on local filesystem (limit is disk, not GARD).
**Constraints**: Append-only audit log roles unchanged (Constitution V); every classification carries the F1 envelope shape (state, summary, facts, reasons, recommended_actions, confidence, as_of, correlation_id); zero silent defaults — missing observations stay `null`, missing-target devices stay in `classified` (Constitution III); MCP exposes exactly five new bounded read tools (Constitution VI); catalog mutations require a git push, not a role (strengthens Constitution IV).
**Scale/Scope**: v1 catalog targets ≤ 200 `FirmwareTarget` rows, ≤ 1,000 `FirmwarePackage` rows, ≤ 500 `UpgradePath` edges, ≤ 200 `PrerequisiteRule` rows. Single CSP estate up to ~50,000 devices, single deployment.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0.

| Principle | Status | How this plan complies |
|---|---|---|
| I. Governance Before Execution | ✅ | F2 still has **no** device-mutation surface. The catalog is policy; the compliance endpoint is read-only. The only state-mutating administrative path is the catalog loader, which is RBAC-gated transitively (it runs on app boot, on `gard catalog reload` CLI by an authenticated operator, or via the existing `lifecycle_manager` role). Approval gate = the upstream PR merge, which lives in Git review, not the application. |
| II. Desired ↔ Actual State Separation | ✅ | F2 is **the moment** desired state is introduced into the system. `FirmwareTarget` is desired state; `Device.observed_firmware` (from F1) is actual; the new lifecycle states `target_defined / compliant / outside_target` are **derived** by the F2 controller, never written by an adapter. F3 will extend the same separation pattern. |
| III. Unknown Is a First-Class State | ✅ | `state=unknown` is the explicit response when `observed_firmware` is `null` (FR-013), when the catalog is empty (AC-1.5), when no target matches the device (FR-014 keeps the device in `classified` — never silently maps to `compliant`), and when a prerequisite predicate is `tagged_with` (FR-024, `evaluable=false` + `predicate_deferred`). Three new device columns (`ram_mb`, `disk_mb`, `licenses`) are explicitly nullable; CSV import never coerces them. |
| IV. Lifecycle-as-Code | ✅ | This feature **mechanizes** lifecycle-as-code for firmware: every catalog entity lives as YAML, every load is anchored to a git commit SHA, removal of a YAML file removes the entity from the live API. There is no in-app catalog editor; approval = merged PR. ADR-0011 codifies the catalog YAML schema and the git-precedence model. |
| V. Evidence, Audit & Explainability (NON-NEGOTIABLE) | ✅ | Every catalog mutation (load, remove, failed-load) emits an `AuditEvent` carrying `loaded_from_git_sha` (FR-039); every blob upload emits both an `AuditEvent` and a `LifecycleEvidence` row with the SHA-256 as `source_checksum` (FR-040); every compliance evaluation emits an `AuditEvent` with `before/after` lifecycle states (FR-041); the compliance response carries the F1 envelope verbatim with `reasons[]` citing the matched target + version comparison + any runner-up targets (FR-011, FR-012). The append-only DB role established in F1 is unchanged (FR-042). |
| VI. MCP Exposes Curated Tools, Not Raw Infrastructure | ✅ | F2 adds exactly five MCP tools — all read-only, all bounded — and **deliberately omits** the `propose_firmware_target_draft` tool we considered in scoping. No MCP catalog-mutation surface in v1; defer to F5 (uplift planning). Each tool reuses F1's auth dependency and audit emit. The disallowed-tool envelope is preserved (FR-036). |
| VII. Integration Over Replacement | ✅ | F2 does not replace any inventory system. Tags from NetBox (Principle VII's identity boundary) are explicitly deferred — the `tagged_with` predicate is loadable but `evaluable=false` until F7. No vendor SDK, no vendor-portal scraping; firmware metadata is operator-authored YAML. Optional `download_url` field on `FirmwarePackage` documents but does not exercise the vendor side. |

**Additional Constraints**: Security — package integrity (Constitution §Security) is *strengthened* by F2 via chunked SHA-256 on write and on every read. Secrets — no new secret introduced; `GARD_BLOB_ROOT` is a path, not a credential. Quality — every new contract surface gets a contract test (REST, MCP, catalog YAML, prereq grammar). Architecture Boundaries — controllers (`firmware_catalog_controller`, `compliance_controller`) do not call adapters (no adapters in F2); cross-controller flow is via persisted state.

**Result**: **PASS, no exceptions required.** Complexity Tracking section omitted.

### Post-design re-check (after Phase 1)

Re-evaluated after writing `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`:

- **Principle II** holds and is *reinforced* by the data model: the new lifecycle states sit on `Device`, derived by a single controller, with no path for an adapter to write them; `FirmwareTarget` rows are loader-write-only (no API mutation).
- **Principle III** is enforced concretely in the contracts: the JSON Schema for `firmware-compliance` response makes `state` an enum that includes `unknown`, the OpenAPI marks `target_ref` and `observed_version` as nullable, and `reasons[0].kind` discriminator distinguishes `missing_observation` / `no_target_matched` / `empty_catalog` so explanation never collapses to a single string.
- **Principle IV** survived a design pressure test: I considered allowing in-app catalog edits (an `Approver` role pushing back changes to YAML via a git-add tool). Rejected. The cost is a small in-process git client and a webhook for "PR merged → reload"; the upside (no in-app approval workflow, single source of truth for catalog state) is large. The decision is binding in ADR-0011 and recorded as R-7 in research.md.
- **Principle V** is mechanized via three concrete audit-emit families in `data-model.md`: `firmware_catalog.{target,package,upgrade_path,prerequisite}.{loaded,removed,reload_failed}`, `firmware_target.compliance_evaluated`, and `firmware_catalog.package.{blob_stored,blob_read_failed}`. Every emit shares the F1 helper.
- **Principle VI** held through the contract pass — the MCP tool schemas in `contracts/mcp-tools.yaml` are bounded (max 500 list items, no free-form predicates over the wire) and reuse the F1 envelope shape.

**Result**: **PASS confirmed post-design.** No new violations introduced. Complexity Tracking section omitted.

## Project Structure

### Documentation (this feature)

```text
specs/002-firmware-catalog/
├── plan.md                      # This file
├── research.md                  # Phase 0 output — binding decisions D1–D8 + R-1…R-9
├── data-model.md                # Phase 1 output — 4 new entities, 3 new device fields, state machine
├── contracts/                   # Phase 1 output
│   ├── rest-openapi.yaml        # F2 REST additions (firmware/* + /firmware-compliance)
│   ├── mcp-tools.yaml           # 5 new read-only MCP tools
│   ├── firmware-target.schema.yaml      # JSON Schema 2020-12 for target YAML
│   ├── firmware-package.schema.yaml     # JSON Schema 2020-12 for package YAML
│   ├── firmware-upgrade-path.schema.yaml
│   ├── firmware-prerequisite.schema.yaml
│   └── scope-selector.schema.yaml       # Shared selector grammar
├── quickstart.md                # Phase 1 output — operator walkthrough
├── checklists/
│   └── requirements.md          # From /speckit-specify
└── tasks.md                     # Phase 2 output — created by /speckit-tasks
```

### Source Code (repository root)

```text
gard/                                       # The product code (continues F1 layout)
├── api/
│   ├── routers/
│   │   ├── firmware_targets.py             # GET /api/v1/firmware/targets[/{id}]
│   │   ├── firmware_packages.py            # GET + blob upload/download
│   │   ├── firmware_upgrade_paths.py       # GET + shortest-path lookup
│   │   ├── firmware_prerequisites.py       # GET only (no eval until F4)
│   │   ├── firmware_compliance.py          # GET /api/v1/devices/{id}/firmware-compliance
│   │   └── …                               # F1 routers unchanged
│   ├── middleware/                         # unchanged
│   └── schemas/
│       ├── firmware_target.py
│       ├── firmware_package.py
│       ├── firmware_upgrade_path.py
│       ├── firmware_prerequisite.py
│       └── firmware_compliance.py          # Envelope variant: target_ref + version comparison
├── mcp/
│   └── tools/
│       ├── get_target_firmware.py
│       ├── get_upgrade_path.py
│       ├── list_firmware_targets.py
│       ├── list_firmware_packages.py
│       └── list_upgrade_paths.py
├── core/
│   ├── firmware_catalog_loader.py          # YAML → JSON Schema validation → upsert
│   ├── firmware_catalog_controller.py      # Loader orchestration + git SHA capture
│   ├── compliance_controller.py            # Resolve target → emit transition → return envelope
│   ├── scope_selector.py                   # Shared selector evaluator
│   ├── upgrade_path_graph.py               # networkx wrapper + Dijkstra
│   ├── blob_store/                         # NEW package
│   │   ├── __init__.py                     # `BlobStore` protocol
│   │   └── local_fs.py                     # `LocalFsBlobStore` implementation
│   └── …                                   # F1 audit.py, evidence.py reused unchanged
├── models/
│   ├── firmware_target.py
│   ├── firmware_package.py
│   ├── firmware_upgrade_path.py
│   ├── firmware_prerequisite.py
│   └── _enums.py                           # extended: target_defined, compliant, outside_target
├── db/
│   └── migrations/versions/
│       └── 0002_firmware_catalog.py        # 4 new tables + 3 device cols + enum extension
├── catalog/                                # extended
│   └── firmware_loader.py                  # entry point used by app boot + CLI
├── __main__.py                             # `gard catalog reload firmware` subcommand
└── …

gard-catalog/                               # Lifecycle-as-Code seed catalog
├── normalization/                          # F1 unchanged
└── firmware/                               # NEW
    ├── targets/
    │   ├── cisco-iosxr-edge.yaml
    │   └── juniper-junos-core.yaml
    ├── packages/
    │   ├── cisco-iosxr-7.5.2.yaml
    │   └── juniper-junos-22.4R3-S2.yaml
    ├── upgrade-paths/
    │   ├── cisco-iosxr.yaml
    │   └── juniper-junos.yaml
    └── prerequisites/
        └── iosxr-minimum-disk.yaml

deploy/
├── docker-compose.yml                      # + deploy_gard-blobs volume
├── scripts/
│   ├── seed.sh                             # extended to load firmware catalog
│   └── fixtures/
│       ├── devices.csv                     # F1 unchanged
│       └── firmware/                       # NEW — mirrors gard-catalog/firmware/ for seed
└── …

adr/
└── ADR-0011-catalog-yaml-schema-and-precedence.md   # NEW

tests/
├── contract/
│   ├── test_firmware_target_yaml_schema.py
│   ├── test_firmware_package_yaml_schema.py
│   ├── test_firmware_upgrade_path_yaml_schema.py
│   ├── test_firmware_prerequisite_yaml_schema.py
│   ├── test_firmware_rest_openapi.py
│   ├── test_firmware_mcp_tools.py
│   └── test_firmware_compliance_envelope.py
├── integration/
│   ├── test_us1_firmware_compliance_per_device.py
│   ├── test_us2_git_native_target_authoring.py
│   ├── test_us3_upgrade_path_and_prerequisites.py
│   ├── test_us4_blob_upload_download.py
│   ├── test_us5_mcp_firmware_tools.py
│   ├── test_loader_transactional_rollback.py
│   ├── test_compliance_state_machine.py
│   └── test_catalog_reload_audit_chain.py
└── unit/
    ├── test_scope_selector_specificity.py
    ├── test_upgrade_path_dijkstra.py
    ├── test_blob_store_local_fs.py
    └── test_prerequisite_grammar.py
```

**Structure Decision**: Continues F1's single-backend layout — F2 adds routers, controllers, models, and a new `blob_store/` package under the existing `gard/` tree without introducing new top-level directories. The `gard-catalog/firmware/` tree mirrors `gard-catalog/normalization/`'s pattern so operators only learn one mental model. ADR-0011 ships in this PR alongside the implementation; F1's ADR-0006 through ADR-0010 remain unchanged. The compose stack gains exactly one new named volume (`deploy_gard-blobs`) and one new environment variable (`GARD_BLOB_ROOT`); no new service.

## Complexity Tracking

Constitution Check passed both pre- and post-design with no violations. This section is intentionally empty.
