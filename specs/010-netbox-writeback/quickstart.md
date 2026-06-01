# F10 — NetBox lifecycle write-back quickstart

Push GARD lifecycle metadata to NetBox **automatically after sync** (custom fields + tags).

## Prerequisites

- F7 read sync working (`netbox_linked > 0`)
- F9 device-type bootstrap completed (recommended for credible DCIM)
- Compliance/readiness evaluations run **before** sync when you need fresh mirrors
- NetBox **write** token (v2 Bearer format)
- Dev: custom fields bootstrapped (step 2 below)

## 1. Configure GARD

```bash
export GARD_NETBOX_URL=http://127.0.0.1:18888          # host URL for CLI
# In Docker API container use host.docker.internal:18888
export GARD_NETBOX_TOKEN=<read-token>                  # F7 pull
export GARD_NETBOX_WRITE_TOKEN=<write-token>           # F10 write-back
export GARD_NETBOX_VERIFY_TLS=false
export GARD_NETBOX_WRITEBACK_ENABLED=true
```

## 2. Bootstrap NetBox custom fields (dev/lab only)

```bash
eval "$(./deploy/scripts/netbox-create-seed-token.sh)"
export GARD_NETBOX_WRITE_TOKEN=$NETBOX_SEED_TOKEN

uv run python -m gard netbox bootstrap-writeback-fields
# Creates extras.custom_fields + tags from gard-catalog/netbox/write-back-manifest.yaml
```

Production: create the same custom fields and tags in NetBox manually (or IaC); GARD does not auto-provision in prod.

## 3. Evaluate lifecycle (recommended before sync)

```bash
JWT=$(cat .gard/netbox-sync.jwt)

curl -X POST -H "Authorization: Bearer $JWT" \
  http://127.0.0.1:8080/api/v1/compliance/evaluate

curl -X POST -H "Authorization: Bearer $JWT" \
  http://127.0.0.1:8080/api/v1/readiness/evaluate
```

## 4. Sync + write-back (single call)

```bash
curl -X POST -H "Authorization: Bearer $JWT" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/sync"
```

Response includes `data.report.writeback` with per-phase summary. HTTP **200** even if some devices fail write-back (pull succeeded).

### Production confirm

```bash
curl -X POST -H "Authorization: Bearer $JWT" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/sync?confirm_writeback=true"
```

## 5. Verify in NetBox UI

Open a linked device → **Custom fields** tab should show `gard_*` fields; **Tags** should include `gard-managed` and posture tags (`gard-drift-outside-target`, etc.) when evaluations warrant.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `writeback.phase=skipped` | Set `GARD_NETBOX_WRITE_TOKEN`; enable `GARD_NETBOX_WRITEBACK_ENABLED` |
| Per-device `failed` missing custom field | Run dev bootstrap or create field in NetBox |
| `conflict` on custom field | Operator edited NetBox field; resolve manually or use future `--force` policy |
| Stale values in NetBox | Run compliance/readiness evaluate before sync |
| Tags reappear after removal | Expected — GARD reconciles manifest tags each sync |

## Related

- F7 quickstart: `specs/007-netbox-integration-read/quickstart.md`
- F9 bootstrap: `specs/009-netbox-devicetype-bootstrap/quickstart.md`
- Manifest: `gard-catalog/netbox/write-back-manifest.yaml`
- ADR-0021 (planned): write-back boundary
