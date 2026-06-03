# F12 — NetBox IPAM & DCIM Alignment Quickstart

Operator runbook for validating IP/VRF/VLAN/overlay alignment after NetBox sync.

## Prerequisites

- F7–F11 shipped; NetBox linked devices present (`netbox_device_id` populated)
- NetBox read token with permissions:
  - `dcim.view_device`, `dcim.view_interface`
  - `ipam.view_ipaddress`, `ipam.view_vrf`, `ipam.view_vlan`
  - L2VPN plugin views if overlay checks enabled
- Alignment policy manifest at `gard-catalog/netbox/alignment-policy-manifest.yaml`

```bash
docker compose -f deploy/docker-compose.yml up -d
curl -sf http://127.0.0.1:8080/healthz
```

## 1. Review alignment policy

Edit site/role expectations before first run:

```bash
${EDITOR:-vi} gard-catalog/netbox/alignment-policy-manifest.yaml
```

Validate schema:

```bash
uv run pytest tests/contract/test_netbox_alignment_manifest.py -q
```

## Upstream NetBox platform (F13)

GARD reads merged NetBox REST state on `main` only. To populate NetBox via **Orb → Diode → NetBox** and practice **merge-to-main before sync**, use the F13 platform lab:

- [specs/013-netbox-platform-lab/quickstart.md](../013-netbox-platform-lab/quickstart.md) — ingest smoke, branch merge demo, GARD handoff
- [ADR-0024](../../adr/ADR-0024-netbox-platform-lab-boundary.md) — deploy-only boundary

Legacy minimal lab: `deploy/scripts/seed-netbox.sh` remains valid (FR-011 alternate path).

## 2. Run sync (triggers alignment)

```bash
TOKEN=$(make token | tail -1)
curl -s -H "Authorization: Bearer $TOKEN" \
  -X POST "http://127.0.0.1:8080/api/v1/integrations/netbox/sync" \
  | python3 -m json.tool
```

Inspect `report.ipam_alignment` in the response:

- `summary.devices_checked`
- `summary.mismatch_count`
- `summary.findings_by_kind`
- `entries[]` per-device rollup

## 3. List findings

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/alignment/findings?severity=error&limit=20" \
  | python3 -m json.tool
```

Filter by device:

```bash
DEVICE_ID="<uuid>"
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/alignment/findings?device_id=$DEVICE_ID" \
  | python3 -m json.tool
```

## 4. Device network context

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$DEVICE_ID/network-context" \
  | python3 -m json.tool
```

Shows interfaces, addresses, VRF/VLAN assignments, and overlay bindings from the latest alignment run.

## 5. Operator portal

1. Open **NetBox** page — alignment summary cards after sync
2. Open **Devices → detail → Network** tab — findings + interface table
3. Re-run sync from the portal; alignment runs automatically (no separate button in v1)

## 6. Optional write-back mirror (F10 extension)

When write-back is enabled, extend `gard-catalog/netbox/write-back-manifest.yaml` with:

- Custom field `gard_ipam_alignment_status`
- Tag `gard-ipam-mismatch` (when error-severity findings exist)

Bootstrap fields in dev:

```bash
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard netbox bootstrap-writeback-fields
```

## Seeded drift fixture (lab)

After implementation, run integration seed that plants:

| Device | Planted drift | Expected kind |
|--------|---------------|---------------|
| edge-osl-006 | Empty `observed_firmware` in CSV; NetBox mgmt IP set | `mgmt_ip_missing_in_gard` or `mgmt_ip_match` depending on GARD row |
| Lab-only row | GARD mgmt IP ≠ NetBox primary | `mgmt_ip_mismatch` |
| Lab-only row | Access port without VLAN | `access_vlan_missing` |

```bash
uv run pytest tests/integration/test_netbox_ipam_alignment.py -q
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `ipam_alignment.phase=skipped` | Zero NetBox-linked devices or `GARD_NETBOX_IPAM_ALIGNMENT_ENABLED=false` |
| `l2vpn_module_unavailable` | NetBox lacks L2VPN plugin — overlay checks skipped (expected) |
| All devices `mgmt_ip_ambiguous` | Multiple primary IPs in NetBox — fix NetBox designation |
| Slow sync | Reduce batch size via `GARD_NETBOX_SYNC_MAX_DEVICES`; check NetBox rate limits |

## Settings (implementation)

| Env var | Default | Purpose |
|---------|---------|---------|
| `GARD_NETBOX_IPAM_ALIGNMENT_ENABLED` | `true` | Master switch |
| `GARD_NETBOX_ALIGNMENT_MANIFEST_PATH` | *(default catalog path)* | Policy path |
| `GARD_NETBOX_IPAM_PREFETCH_CONCURRENCY` | `8` | Parallel NetBox prefetch workers |
