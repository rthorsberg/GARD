# NetBox IPAM drift fixtures (F12)

Planted drift scenarios for integration and lab validation:

| Scenario | Setup | Expected finding |
|----------|-------|------------------|
| Mgmt IP mismatch | GARD CSV `management_ip` differs from NetBox `primary_ip4` | `mgmt_ip_mismatch` |
| Missing uplink IP | Edge device interface `Gi0/1` enabled without IPAM assignment | `interface_missing_address` |
| VRF drift | `mgmt0` interface VRF not `mgmt` on Oslo edge | `vrf_mismatch` |
| Access VLAN missing | Access port without untagged VLAN in Oslo VLAN group | `access_vlan_missing` |

Run `POST /api/v1/integrations/netbox/sync` after seeding NetBox lab data and importing matching GARD CSV rows.
