# NetBox and TR-069 Positioning

## NetBox Relationship

GARD should be a standalone lifecycle platform with first-class NetBox integration, not only a NetBox plugin.

### Ownership Boundary

```text
NetBox = what exists and where it belongs
GARD   = what software state it should have and how to get there safely
```

### NetBox-owned/reference data

- device name
- manufacturer
- device type/model
- platform
- site/location/rack
- role
- serial number
- management IP
- tags
- interface/topology references where relevant

### GARD-owned lifecycle data

- firmware target catalogue
- approved/deprecated/blocked versions
- firmware package metadata
- upgrade paths
- prerequisites
- compliance/readiness/risk state
- uplift plans/waves/workflows
- exceptions
- lifecycle evidence
- MCP tools and audit

### Recommended NetBox Integration Phases

1. API pull from NetBox into GARD.
2. Write summary lifecycle custom fields back to NetBox.
3. Optional NetBox plugin with device lifecycle panel and bulk actions.
4. Use NetBox topology/dependency data for blast-radius controls.

### NetBox Plugin Scope

The plugin should show:

- current firmware
- target firmware
- compliance state
- readiness state
- risk score
- last evaluated
- link to GARD record
- blocking reasons

The plugin should not:

- host firmware files
- execute upgrades directly
- run MCP tools unrestricted
- implement long-running workflow queues

## TR-069 / TR-369 Relationship

TR-069/ACS and TR-369/USP are important southbound execution systems, especially for CPE.

GARD should not replace a mature ACS where it already performs:

- device communication
- parameter management
- firmware download
- transfer result reporting
- diagnostics

Instead:

```text
ACS performs device management.
GARD performs lifecycle governance.
```

## TR-069 Adapter Concept

For TR-069-managed devices, GARD should be able to:

1. Import/query device identity and software version from ACS.
2. Map TR-181 parameters to GARD lifecycle inventory.
3. Evaluate compliance against GARD target firmware policy.
4. Create uplift plans and waves.
5. Ask ACS adapter to schedule/trigger firmware download.
6. Poll/receive transfer result.
7. Validate post-upgrade software version.
8. Record LifecycleEvidence.

## Integration Rule

> TR-069 is one southbound adapter. It is not the GARD core domain.
