# F12 — Data Model

F12 adds alignment persistence, a policy manifest catalogue artefact, and REST read models. NetBox remains authoritative for IPAM/DCIM/L2VPN objects.

## Alignment Policy Manifest (catalog artefact)

**Location**: `gard-catalog/netbox/alignment-policy-manifest.yaml`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | `"1"` |
| `mgmt_ip` | object | yes | Resolution + comparison rules |
| `interface_policies` | array | yes | Per role/site expectations |
| `vrf_expectations` | array | no | Expected VRF slug per site+role+interface pattern |
| `vlan_expectations` | array | no | VLAN group scope + access/trunk rules |
| `overlay_expectations` | array | no | L2VPN service slug → expected RTs |
| `severity_overrides` | object | no | Map finding kind → severity |

### `mgmt_ip` section

| Field | Type | Notes |
|-------|------|-------|
| `interface_name_patterns` | string[] | Regex for management-like interfaces |
| `prefer_ipv4` | boolean | default true |
| `require_assignment` | boolean | When true, missing NetBox IP → error for prod roles |

### Interface policy row

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Stable policy id |
| `site` | string | NetBox site slug or `*` |
| `role` | string | NetBox role slug or `*` |
| `interface_pattern` | string | Regex on interface name |
| `require_ip` | boolean | Enabled interface must have IPAM assignment |
| `allowed_modes` | string[] | e.g. `access`, `tagged`, `tagged-all` |

**Validation rules** (FR-015):

- Unique policy `id` values
- Referenced site/role slugs must exist in manifest `sites[]` / `roles[]` catalogue section OR be `*`
- VLAN group references must appear in `vlan_groups[]` catalogue section
- VRF references must appear in `vrfs[]` catalogue section when not wildcard

## Postgres: `ipam_alignment_runs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | uuid7 |
| `netbox_sync_run_id` | UUID FK | → `netbox_sync_runs.id`, unique |
| `status` | enum | `completed`, `partial`, `failed`, `skipped` |
| `devices_checked` | int | |
| `findings_error_count` | int | |
| `findings_warning_count` | int | |
| `findings_info_count` | int | |
| `l2vpn_available` | bool | |
| `started_at` | timestamptz | |
| `completed_at` | timestamptz | nullable |
| `correlation_id` | varchar(64) | |
| `actor` | varchar(255) | |

**Skipped** when alignment disabled or zero netbox-linked devices in batch.

## Postgres: `ipam_alignment_findings`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `run_id` | UUID FK | → `ipam_alignment_runs.id` |
| `device_id` | UUID FK | → `devices.id` |
| `kind` | varchar(64) | Closed enum — see contracts |
| `severity` | enum | `error`, `warning`, `info` |
| `status` | enum | `open`, `pass` — `pass` for positive checks e.g. mgmt_ip_match |
| `netbox_observed` | JSONB | Snapshot fragment |
| `gard_observed` | JSONB | Snapshot fragment |
| `remediation_hint` | text | nullable |
| `interface_name` | varchar(128) | nullable |
| `created_at` | timestamptz | |

**Indexes**:

- `(run_id, device_id)`
- `(device_id, created_at DESC)`
- `(kind)` partial where `status = open`

## Postgres: `device_network_contexts`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `run_id` | UUID FK | |
| `device_id` | UUID FK | |
| `netbox_device_id` | int | |
| `primary_ip4` | varchar(64) | nullable, CIDR or host |
| `primary_ip6` | varchar(64) | nullable |
| `resolved_mgmt_ip` | varchar(64) | nullable, host only |
| `mgmt_resolution_method` | varchar(64) | e.g. `primary_ip4`, `mgmt_interface` |
| `interfaces` | JSONB | Array of normalized interface records |
| `overlay_bindings` | JSONB | L2VPN/EVPN correlations |
| `captured_at` | timestamptz | |

**Interface JSON shape** (stored, not normalized tables):

```yaml
name: string
enabled: bool
mode: string | null
mgmt_only: bool
vrf: { id, name, rd } | null
untagged_vlan: { id, vid, name } | null
tagged_vlans: [{ id, vid, name }]
addresses: [{ address, family, primary, vrf }]
```

## Ephemeral: Alignment report (sync API)

| Field | Type | Notes |
|-------|------|-------|
| `phase` | enum | `completed`, `partial`, `failed`, `skipped` |
| `summary` | object | Counts by severity and kind |
| `entries` | array | Truncated per-device rollup (cap 100 in sync response) |
| `run_id` | uuid | |

### Entry rollup

| Field | Type | Notes |
|-------|------|-------|
| `device_id` | uuid | |
| `netbox_device_id` | int | |
| `overall_status` | enum | `aligned`, `mismatch`, `unknown` |
| `finding_count` | int | |
| `top_kinds` | string[] | Up to 3 kinds |

## GARD `devices` (optional columns)

| Column | Type | Notes |
|--------|------|-------|
| `netbox_last_alignment_at` | timestamptz | nullable |
| `netbox_alignment_status` | varchar(32) | nullable enum string cache for list views |

Migration: `0012_ipam_alignment.py`.

## Finding kind catalogue

See `contracts/finding-kinds.yaml` for the closed enum and default severities.

Categories:

| Category | Example kinds |
|----------|----------------|
| Management IP | `mgmt_ip_match`, `mgmt_ip_mismatch`, `mgmt_ip_missing_in_netbox`, `mgmt_ip_missing_in_gard`, `mgmt_ip_ambiguous`, `mgmt_ip_fallback_used` |
| Interface/IPAM | `interface_ip_bound`, `interface_missing_address`, `prefix_vrf_scope_mismatch`, `cross_device_address_conflict`, `shared_address` |
| VRF | `vrf_mismatch`, `vrf_orphaned_in_site` |
| VLAN | `access_vlan_missing`, `vlan_out_of_scope`, `vlan_aligned` |
| Overlay | `overlay_rt_aligned`, `rt_missing_on_interface`, `rt_import_missing`, `rt_export_missing`, `l2vpn_module_unavailable` |

## Relationships

```text
NetboxSyncRun 1──0..1 IpamAlignmentRun
IpamAlignmentRun 1──* IpamAlignmentFinding
IpamAlignmentRun 1──* DeviceNetworkContext
Device 1──* IpamAlignmentFinding (via device_id)
Device 1──0..1 DeviceNetworkContext (latest by captured_at)
AlignmentPolicyManifest (YAML) ──evaluates──▶ findings
NetBox REST (external) ──snapshots──▶ DeviceNetworkContext
```

## State transitions

**IpamAlignmentRun**:

```text
started → completed | partial | failed
skipped (alignment disabled or no linked devices)
```

**Finding**: immutable once written for a run; new sync run produces new finding rows.

## External NetBox objects (read-only)

| NetBox object | F12 action |
|---------------|------------|
| `dcim.Device` | Read primary/oob IP fields |
| `dcim.Interface` | Read mode, VLAN, VRF |
| `ipam.IPAddress` | Read assignments |
| `ipam.VRF` | Read for scope checks |
| `ipam.VLAN` / `VLANGroup` | Read for scope checks |
| `plugins.l2vpn.*` | Read when plugin present |

**Never mutated in v1** (FR-010).
