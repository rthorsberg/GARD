# F13 — NetBox Platform Lab: Research

**Feature**: `013-netbox-platform-lab` | **Date**: 2026-06-02

## R-1 — Compose topology and project isolation

**Decision**: Extend the existing F7 stack under compose project **`gard-f7-netbox`** with a second compose file overlay:

```bash
docker compose -p gard-f7-netbox \
  -f deploy/netbox/docker-compose.yml \
  -f deploy/netbox/docker-compose.platform.yml \
  --env-file deploy/netbox/.env up -d
```

NetBox core (`postgres`, `redis`, `netbox`, `netbox-worker`) stays in the base file. Diode server containers, Orb agent, and lab simulator hosts live in `docker-compose.platform.yml`. All volumes remain prefixed by the compose project name.

**Rationale**: Spec FR-002 requires isolation from GARD (`deploy` project, port 8080) and other NetBox labs (18080). Reusing `gard-f7-netbox` preserves F7 token URLs (`host.docker.internal:18888`) and avoids port churn.

**Alternatives considered**:
- Separate project `gard-f13-platform` with new NetBox instance — rejected (duplicate NetBox, breaks F7 quickstart URLs).
- Single monolithic compose file — rejected (harder to run minimal F7-only lab without Diode).

## R-2 — NetBox plugins (Diode + Branching)

**Decision**: Build a custom NetBox image via `deploy/netbox/Dockerfile.plugins`:

- Base: `netboxcommunity/netbox:v4.6-5.0.1` (matches current F7 pin)
- Install: `netboxlabs-diode-netbox-plugin` (required for ingest path)
- Optional install: `netboxlabs-netbox-branching` when `GARD_NETBOX_BRANCHING_ENABLED=1`
- `PLUGINS` order: `["netbox_diode_plugin", "netbox_branching"]` — **branching MUST be last**
- `DATABASE_ROUTERS` includes `netbox_branching.database.BranchAwareRouter` when Branching enabled
- Diode plugin config: `diode_target_override`, `netbox_to_diode_client_secret` from env (not committed)

**Rationale**: Official NetBox Labs docs require plugin install + migrations for both Diode reconciler callbacks and Branching schema isolation. Pinning to F7 NetBox version avoids surprise API drift.

**Alternatives considered**:
- Runtime `pip install` in entrypoint — rejected (slow, non-reproducible).
- Branching-only without Diode — rejected (spec primary narrative is Orb → Diode → NetBox).

## R-3 — Diode server deployment and NetBox reachability

**Decision**: Vendor the Diode quickstart layout under `deploy/netbox/platform/diode/` (compose, nginx, env template). Critical env:

- `NETBOX_DIODE_PLUGIN_API_BASE_URL=http://netbox:8080` (Docker service DNS, **not** `127.0.0.1`)
- OAuth client secret for `netbox-to-diode` generated at bootstrap; stored in operator-local `.env` (FR-008)

Bootstrap script extracts `netbox-to-diode` secret and prints Diode Orb client credential creation steps (NetBox UI: Diode → Client Credentials).

**Rationale**: Diode reconciler failures commonly occur when reconciler cannot reach NetBox plugin endpoints from inside the container (netboxlabs/diode#521). Using compose service name matches Docker network reality.

**Alternatives considered**:
- Host-installed Diode at `/opt/diode` — rejected (not reproducible from repo).
- `host.docker.internal` for reconciler — rejected (Linux/macOS variance; service DNS is portable within compose).

## R-4 — Orb agent lab configuration

**Decision**: Run `netboxlabs/orb-agent:latest` as a compose service with mounted `deploy/netbox/platform/orb/agent.yaml`:

- `backends.network_discovery` policy scoped to **`platform-lab` bridge subnet** (e.g. `172.30.77.0/24`)
- Targets: 3 lightweight **simulator containers** (Alpine + static hostname) on predictable IPs
- Diode target: `grpc://diode-nginx:8080/diode` (internal compose DNS)
- Credentials via env: `DIODE_CLIENT_ID`, `DIODE_CLIENT_SECRET` (from NetBox UI, not in git)

Use `cap_add: [NET_RAW]` and bridge networking (not host mode) so macOS/Windows Docker Desktop behave consistently; simulators respond to ICMP for deterministic discovery.

**Rationale**: Spec FR-003 requires Orb → Diode → NetBox without manual REST seeding. Fixture-scoped discovery on simulator containers exercises the real pipeline while staying deterministic (SC-002, edge case: limit discovery scope).

**Alternatives considered**:
- Host-network Orb scanning operator LAN — rejected (non-deterministic, security concern).
- Orb `dry_run` only — rejected (does not prove Diode ingest).
- Direct Diode gRPC fixture inject without Orb — rejected as primary path (spec names Orb as primary narrative); may document as troubleshooting fallback only.

## R-5 — Ingest fixture catalogue format

**Decision**: Versioned YAML at `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` validated by `contracts/ingest-fixture-catalogue.schema.yaml`:

- `schema_version: "1"`
- `devices[]`: `name`, `site`, `role`, `device_type`, `serial`, `expected_primary_ip` (optional), `simulator_ip`
- `minimum_device_count: 3` for smoke pass
- `idempotency_notes`: document second-run expectations (Diode upsert behavior)

Smoke script queries NetBox REST (`GET /api/dcim/devices/?name=`) and compares counts/names to catalogue.

**Rationale**: Constitution IV (lifecycle-as-code for lab artefacts); SC-002 measurable outcome; contract tests gate fixture drift.

**Alternatives considered**:
- Unstructured README only — rejected (not machine-verifiable).
- Checking only object counts — rejected (misses wrong-device false positives).

## R-6 — Branching workflow and GARD read boundary

**Decision**: Document and automate a **merge checkpoint** workflow:

1. Confirm GARD reads `main`: `GET /api/dcim/devices/` without branch header shows pre-change IP
2. Create branch via NetBox Branching UI or REST; modify management IP on seeded device
3. Re-query `main` — change **not** visible (SC-003 before check)
4. Merge branch (`MergeBranchJob`); wait for job `completed`
5. Re-query `main` — change visible
6. Run `./deploy/scripts/sync-gard-netbox.sh`; verify F12 alignment reflects merged IP

When Branching disabled (`GARD_NETBOX_BRANCHING_ENABLED=0`), alternate path: direct edit on `main` + same GARD sync steps (FR-011).

**Rationale**: ADR-0018/0023 and spec User Story 3 — GARD never observes unmerged branch state. Explicit before/after REST checks make the anti-pattern visible.

**Alternatives considered**:
- Branch-only validation without GARD — insufficient for User Story 4 cross-link.
- GARD branch-aware reads — rejected (violates ADR-0018 v1 boundary).

## R-7 — Credential bootstrap (no secrets in repo)

**Decision**: Document bootstrap in quickstart:

| Credential | Source | Storage |
|---|---|---|
| NetBox superuser | `.env` defaults (dev only) | `deploy/netbox/.env` (gitignored) |
| NetBox API token (GARD) | `netbox-create-seed-token.sh` | `.gard/netbox-sync.jwt` + env |
| Diode `netbox-to-diode` secret | Diode quickstart OAuth JSON | `deploy/netbox/.env` |
| Orb Diode client | NetBox UI Diode → Client Credentials | `deploy/netbox/.env` |

Provide `.env.example` with placeholder keys only (FR-008).

**Rationale**: Constitution Security — secrets not in VCS; matches existing F7 token pattern.

## R-8 — Health checks and smoke contracts

**Decision**: `platform-lab-health.sh` emits JSON validated by `contracts/health-check.schema.yaml`:

```json
{
  "status": "healthy|degraded|unhealthy",
  "checks": [
    {"name": "netbox_ui", "ok": true, "detail": "..."},
    {"name": "diode_grpc", "ok": true},
    {"name": "orb_agent", "ok": true},
    {"name": "netbox_diode_plugin", "ok": true}
  ],
  "branching_enabled": false
}
```

Exit codes: `0` healthy, `1` degraded (Branching skipped but core OK), `2` unhealthy.

**Rationale**: Operator runbook needs machine-readable health for CI optional job and SC-001 30-minute onboarding.

## R-9 — Planted drift scenarios (F12 validation)

**Decision**: Two documented scenarios under `deploy/scripts/fixtures/platform-lab/drift-scenarios/`:

| Scenario | NetBox change | Expected F12 kind | Verification |
|---|---|---|---|
| `mgmt-ip-mismatch.md` | Merge branch changing device primary IP vs GARD CSV | `mgmt_ip_mismatch` | `GET .../alignment/findings?kind=mgmt_ip_mismatch` |
| `missing-interface-address.md` | Remove IP assignment on mgmt interface | `missing_in_netbox` or `mgmt_ip_missing` | findings list + device network context |

Scenarios assume GARD estate CSV still holds pre-change management IPs until operator re-imports or updates GARD device record — documenting **intentional drift** for alignment demo.

**Rationale**: User Story 4, SC-004; connects platform lab to F12 without GARD code changes.

## R-10 — Teardown and volume reset

**Decision**: Document three levels:

| Level | Command | Effect |
|---|---|---|
| Soft stop | `platform-lab-stop.sh` | `docker compose ... down` (no volumes) |
| Platform reset | `down` platform overlay only | Diode/Orb removed; NetBox data kept |
| Full lab wipe | `down -v` with `-p gard-f7-netbox` | **This project volumes only** |

Explicit warnings against `docker system prune` and compose `down -v` without `-p gard-f7-netbox` (FR-009, edge cases).

**Rationale**: Spec edge cases and SC-006 — scoped teardown must not affect GARD stack or other NetBox projects.
