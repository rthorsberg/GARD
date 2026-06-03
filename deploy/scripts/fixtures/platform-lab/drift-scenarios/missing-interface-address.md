# Drift scenario: missing interface address

**Expected F12 finding kind**: `interface_missing_address` or `mgmt_ip_missing_in_netbox`
**Pass criteria**: Finding appears when management interface has no assigned IP in NetBox snapshot.

## Preconditions

- `lab-router-01` synced to GARD with populated `management_ip` in CSV
- Alignment manifest requires IP on management interface pattern (default `(?i)^(mgmt|management|lo0?)`)

## NetBox steps

1. On a branch (or `main` if Branching disabled), remove IP assignment from the management/loopback interface on `lab-router-01`.
2. Merge to `main` if using Branching.
3. Verify interface has no address in NetBox UI or REST.

## GARD verification

```bash
./deploy/scripts/sync-gard-netbox.sh
TOKEN=$(cat .gard/netbox-sync.jwt)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/alignment/findings?severity=error&limit=20" \
  | jq .
```

**Pass**: Finding kind is `interface_missing_address` or `mgmt_ip_missing_in_netbox` for the device.

**Fail**: Sync succeeds but no findings — confirm device is NetBox-linked and alignment phase ran (`report.ipam_alignment` in sync response).

See [F12 quickstart](../../../../specs/012-netbox-ipam-dcim-align/quickstart.md).
