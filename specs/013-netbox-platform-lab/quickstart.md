# F13 — NetBox Platform Lab Quickstart

Operator runbook for the Orb → Diode → NetBox platform lab and merge-to-`main` → GARD sync workflow.

**Scope**: Dev/lab only. No GARD application code changes. Production deployment is out of scope — see [ADR-0018](../../adr/ADR-0018-netbox-diode-assurance-ecosystem.md) and [ADR-0024](../../adr/ADR-0024-netbox-platform-lab-boundary.md).

## Prerequisites

- Docker Compose v2, bash 4+, `curl`, `jq`, `python3`
- ~8 GB RAM free
- Ports available: **18888** (NetBox), **58080** (Diode gRPC default), **55432** (Postgres debug)
- No conflicting NetBox lab on 18888 or GARD stack requirement on 8080/5432

```bash
# Pre-flight port check (example)
for p in 18888 58080; do
  lsof -iTCP:"$p" -sTCP:LISTEN && echo "WARN: port $p in use" || true
done
```

## 1. Configure credentials (no secrets in git)

```bash
cp deploy/netbox/.env.example deploy/netbox/.env
${EDITOR:-vi} deploy/netbox/.env
```

Populate locally (never commit):

| Variable | Purpose |
|---|---|
| `NETBOX_SUPERUSER_PASSWORD` | NetBox admin (dev default OK) |
| `NETBOX_TO_DIODE_CLIENT_SECRET` | From Diode OAuth bootstrap |
| `DIODE_CLIENT_ID` / `DIODE_CLIENT_SECRET` | From NetBox UI → Diode → Client Credentials |
| `GARD_NETBOX_BRANCHING_ENABLED` | `1` to build Branching plugin (optional) |

## 2. Start platform lab

```bash
./deploy/scripts/platform-lab-start.sh
```

Or manually:

```bash
docker compose -p gard-f7-netbox \
  -f deploy/netbox/docker-compose.yml \
  -f deploy/netbox/docker-compose.platform.yml \
  --env-file deploy/netbox/.env up -d --build
```

**Health check**:

```bash
./deploy/scripts/platform-lab-health.sh | jq .
# Expect status: healthy (or degraded if Branching skipped)
```

NetBox UI: [http://127.0.0.1:18888/](http://127.0.0.1:18888/)

## 3. Bootstrap device types (F9)

Orb/Diode ingest expects credible device types — run F9 bootstrap once per fresh NetBox volume:

```bash
git submodule update --init vendor/netbox-devicetype-library
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=$(./deploy/scripts/netbox-create-seed-token.sh | grep NETBOX_SEED_TOKEN | cut -d= -f2)
export GARD_NETBOX_VERIFY_TLS=false
python -m gard netbox bootstrap-device-types
```

See [F9 quickstart](../009-netbox-devicetype-bootstrap/quickstart.md).

## 4. Ingest smoke (Orb → Diode → NetBox)

```bash
./deploy/scripts/platform-lab-ingest-smoke.sh
```

Verifies ≥3 devices from [ingest catalogue](../../deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml) appear on NetBox **`main`** via REST — **without** `seed-netbox.sh` manual REST posts.

Re-run notes: see `idempotency_notes` in the catalogue; inspect Diode reconciler logs on partial failure.

## 5. Branch, merge, verify `main` (optional)

> **Anti-pattern**: Running GARD sync while changes exist only on a Branching branch. GARD reads **`main` only** (ADR-0018, ADR-0023).

When `GARD_NETBOX_BRANCHING_ENABLED=1`:

```bash
./deploy/scripts/platform-lab-merge-demo.sh
```

Manual outline:

1. Record device primary IP on `main` (REST GET)
2. Create branch; change management IP assignment
3. Confirm `main` unchanged (GARD would **not** see branch edit)
4. Merge branch; wait for merge job completion
5. Confirm `main` updated

**Fallback** (Branching skipped): edit `main` directly; same REST before/after checks apply.

## 6. GARD sync handoff

Start GARD stack if not running:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Run existing sync script (F7 + F10 + F12 alignment):

```bash
./deploy/scripts/sync-gard-netbox.sh
```

Cross-links:

- [F7 NetBox read sync](../007-netbox-integration-read/quickstart.md)
- [F12 IPAM alignment](../012-netbox-ipam-dcim-align/quickstart.md) — verify `report.ipam_alignment` and findings endpoints

## 7. Planted drift scenarios (F12 validation)

With GARD estate CSV holding **stale** management IPs relative to merged NetBox state:

| Scenario | Doc |
|---|---|
| Management IP mismatch | [mgmt-ip-mismatch.md](../../deploy/scripts/fixtures/platform-lab/drift-scenarios/mgmt-ip-mismatch.md) |
| Missing interface address | [missing-interface-address.md](../../deploy/scripts/fixtures/platform-lab/drift-scenarios/missing-interface-address.md) |

Expected finding kinds are listed in each scenario README before invoking GARD.

## 8. End-to-end runbook (FR-012)

```text
platform-lab-start → health → F9 bootstrap → ingest-smoke
  → (optional) branch/merge-demo → sync-gard-netbox → F12 findings check
```

Target time: ≤30 minutes excluding image pulls (SC-001).

## Teardown

**Soft stop** (preserve data):

```bash
./deploy/scripts/platform-lab-stop.sh
```

**Intentional volume wipe** (this lab only):

```bash
docker compose -p gard-f7-netbox \
  -f deploy/netbox/docker-compose.yml \
  -f deploy/netbox/docker-compose.platform.yml \
  down -v
```

Never run `docker system prune` or compose `down -v` without `-p gard-f7-netbox`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Diode ingest OK, nothing in NetBox | Reconciler logs; verify `NETBOX_DIODE_PLUGIN_API_BASE_URL=http://netbox:8080` (not localhost) |
| Orb cannot reach Diode | `DIODE_CLIENT_*` credentials; Diode nginx health |
| Branching plugin missing | Rebuild with `GARD_NETBOX_BRANCHING_ENABLED=1` |
| GARD sees old IP after merge | Confirm merge job completed; re-run REST GET on `main` before sync |

## Related

- [deploy/netbox/README.md](../../deploy/netbox/README.md)
- [spec.md](./spec.md) | [plan.md](./plan.md) | [research.md](./research.md)
- [contracts/](./contracts/) — stack manifest, fixture schema, health JSON
