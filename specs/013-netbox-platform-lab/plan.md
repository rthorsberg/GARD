# F13 — NetBox Platform Lab (Orb, Diode, Branching): Implementation Plan

**Feature Branch**: `013-netbox-platform-lab`
**Status**: Draft
**Date**: 2026-06-02
**Inputs**: `spec.md`, `research.md` (R-1..R-10), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F7 (NetBox read sync), F9 (device types), F12 (IPAM alignment), ADR-0018 (ecosystem), ADR-0023 (alignment boundary)
**Successor**: none planned

## Summary

F13 delivers a **dev/lab-only NetBox platform stack** that extends the existing F7 NetBox compose project with Diode ingestion services, an Orb agent, optional NetBox Branching, and operator runbooks. Discovery-shaped fixture data flows **Orb → Diode → NetBox `main`**, operators practice **branch → review → merge → GARD sync**, and planted drift scenarios validate F12 alignment — **without any GARD application code changes** (FR-007).

## Technical Context

| Aspect | Choice |
|---|---|
| Scope | Dev/lab deploy artefacts only — compose, shell scripts, YAML fixtures, docs |
| GARD code | **No changes** to `gard/`, `web/`, migrations, or API (FR-007, SC-005) |
| NetBox base | Extend `deploy/netbox/docker-compose.yml` (`gard-f7-netbox`, port **18888**) |
| NetBox image | Custom build: community NetBox v4.6 + `netboxlabs-diode-netbox-plugin` + optional `netboxlabs-netbox-branching` (branching **last** in `PLUGINS`) |
| Diode | Vendor quickstart pattern vendored under `deploy/netbox/platform/diode/`; reconciler `NETBOX_DIODE_PLUGIN_API_BASE_URL` uses Docker-reachable NetBox URL (not `127.0.0.1`) |
| Orb agent | `netboxlabs/orb-agent:latest` in compose; `network_discovery` scoped to lab bridge subnet + fixture simulator containers |
| Ingest fixtures | Versioned catalogue at `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` (contract-validated) |
| Branching | Optional plugin slice; documented merge-to-`main` via NetBox UI + REST; fallback = direct `main` edits |
| GARD handoff | Existing `./deploy/scripts/sync-gard-netbox.sh` + F7/F12 quickstarts; GARD reads `main` only |
| Testing | Shell contract tests (health + ingest smoke exit codes); optional CI job `platform-lab-smoke` (non-blocking, image-pull heavy) |
| Isolation | Explicit compose project `-p gard-f7-netbox`; documented port overrides; no global Docker prune |
| ADR | **ADR-0024** — platform lab boundary (deploy-only, upstream of GARD) |

## Constitution Check

*GATE: Passed pre-Phase 0 and post-Phase 1 design.*

| Principle | F13 adherence |
|---|---|
| I — Governance Before Execution | Lab is observe/ingest/stage only; no GARD execution or device mutation |
| II — Desired vs Actual | GARD continues to derive alignment from NetBox REST; lab populates NetBox SoT upstream |
| III — Unknown Is First-Class | Drift fixtures document expected F12 finding kinds including `missing_in_gard` / `missing_in_netbox` |
| IV — Lifecycle-as-Code | Ingest catalogue + lab stack manifest are version-controlled YAML with JSON Schema contracts |
| V — Evidence/Audit | No GARD audit changes; lab scripts emit structured JSON health reports for operator evidence |
| VI — Curated MCP | No MCP surface changes |
| VII — Integration Over Replacement | NetBox remains identity SoT; Orb/Diode are upstream population path per ADR-0018 |

**Post-design re-check**: F13 reinforces ADR-0018 layering without introducing GARD Diode SDK integration. ADR-0024 documents deploy boundary. No constitutional violation.

## Project Structure

### Documentation (this feature)

```text
specs/013-netbox-platform-lab/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── lab-stack-manifest.schema.yaml
│   ├── lab-stack-manifest.yaml
│   ├── ingest-fixture-catalogue.schema.yaml
│   └── health-check.schema.yaml
└── tasks.md                                  # /speckit-tasks (generated)
```

### Source Code (repository root)

**New**

- `adr/ADR-0024-netbox-platform-lab-boundary.md`
- `deploy/netbox/Dockerfile.plugins` — NetBox + Diode plugin + optional Branching
- `deploy/netbox/configuration/plugins.py` — plugin config (`BranchAwareRouter`, diode secrets via env)
- `deploy/netbox/docker-compose.platform.yml` — Diode stack + Orb agent + lab simulators
- `deploy/netbox/platform/diode/` — vendored/adapted Diode quickstart (compose, nginx, env template)
- `deploy/netbox/platform/orb/agent.yaml` — fixture-scoped discovery policy
- `deploy/scripts/platform-lab-start.sh` — start NetBox + platform overlay
- `deploy/scripts/platform-lab-stop.sh` — project-scoped stop
- `deploy/scripts/platform-lab-health.sh` — health JSON (contract output)
- `deploy/scripts/platform-lab-ingest-smoke.sh` — trigger Orb policy + assert NetBox counts
- `deploy/scripts/platform-lab-merge-demo.sh` — branch IP change → merge → pre/post REST checks
- `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` — canonical fixture catalogue
- `deploy/scripts/fixtures/platform-lab/drift-scenarios/` — 2+ planted drift READMEs
- `tests/contract/test_platform_lab_manifest.py` — manifest + fixture schema validation
- `tests/contract/test_platform_lab_health_schema.py` — health JSON shape

**Extended**

- `deploy/netbox/docker-compose.yml` — use `Dockerfile.plugins` image when `GARD_NETBOX_PLATFORM=1`
- `deploy/netbox/README.md` — platform lab section, port matrix, isolation warnings
- `deploy/netbox/.env.example` — Diode/Branching/Orb env vars (no secrets committed)
- `specs/007-netbox-integration-read/quickstart.md` — cross-link platform lab ingest path
- `specs/012-netbox-ipam-dcim-align/quickstart.md` — cross-link merge-before-sync workflow
- `ROADMAP.md` — F13 row

**Unchanged**

- `gard/` application source, database, API, UI
- `deploy/scripts/seed-netbox.sh` — remains valid for minimal DCIM-only labs (FR-011 alternate path)
- `deploy/scripts/sync-gard-netbox.sh` — reused for post-merge GARD validation

## PR slices

| Slice | Scope |
|---|---|
| **13a** | ADR-0024, spec/plan/research/contracts, lab-stack manifest, contract tests, ROADMAP row |
| **13b** | Dockerfile.plugins, plugins.py, docker-compose.platform.yml, Diode vendored stack, env templates |
| **13c** | Orb agent + simulator containers, ingest catalogue, ingest-smoke script |
| **13d** | Branching optional slice, merge-demo script, drift scenario fixtures, quickstart + README cross-links |

## Complexity Tracking

No constitution violations requiring justification.

## Phase 0 & 1 outputs (this command)

| Artifact | Path | Status |
|---|---|---|
| Research | `specs/013-netbox-platform-lab/research.md` | Generated |
| Data model | `specs/013-netbox-platform-lab/data-model.md` | Generated |
| Contracts | `specs/013-netbox-platform-lab/contracts/` | Generated |
| Quickstart | `specs/013-netbox-platform-lab/quickstart.md` | Generated |
| Agent context | `.cursor/rules/specify-rules.mdc` | Updated |

## Next

```bash
/speckit-tasks
/speckit-implement
```
