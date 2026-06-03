# Drift scenario: management IP mismatch

**Expected F12 finding kind**: `mgmt_ip_mismatch`
**Pass criteria**: Finding appears for target device after GARD sync with severity ≥ policy default.

## Preconditions

- Platform lab ingest smoke passed (`lab-router-01` on NetBox `main`)
- GARD stack running with devices imported from CSV where `management_ip` **differs** from NetBox merged primary IP
- F9 device types bootstrapped; F12 alignment enabled

## NetBox steps

1. Merge a branch (or edit `main` directly if Branching disabled) changing `lab-router-01` primary IP to an address **not** present in GARD CSV `management_ip`.
2. Confirm on `main` via REST:
   ```bash
   curl -s -H "Authorization: Token $NETBOX_SEED_TOKEN" \
     http://127.0.0.1:18888/api/dcim/devices/?name=lab-router-01 | jq .
   ```

## GARD verification

```bash
./deploy/scripts/sync-gard-netbox.sh
TOKEN=$(cat .gard/netbox-sync.jwt)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/integrations/netbox/alignment/findings?kind=mgmt_ip_mismatch&limit=20" \
  | jq .
```

**Pass**: At least one `mgmt_ip_mismatch` finding references `lab-router-01` (or linked GARD device id).

**Fail**: No finding when NetBox and GARD IPs clearly differ — check alignment manifest site/role scope.

See [F12 quickstart](../../../../specs/012-netbox-ipam-dcim-align/quickstart.md).
