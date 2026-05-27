# Domain Assumptions and Decisions to Validate

## Assumptions

1. The initial GARD implementation starts with CSV import from an external discovery system.
2. Native discovery is a later phase.
3. GARD is standalone with NetBox integration, not only a NetBox plugin.
4. NetBox or another inventory system remains the source of infrastructure identity/reference.
5. GARD owns firmware lifecycle policy and lifecycle state.
6. GARD v1 is governance-first and guided/semi-automated, not fully autonomous.
7. MCP is included from v1, but primarily as read-only/reporting/draft-planning tools.
8. GARD supports TFTP/FTP/HTTP file delivery for legacy and modern devices.
9. TR-069/ACS and TR-369/USP are treated as southbound execution systems for CPE.
10. SEGL is a future certificate/evidence product concept; v1 implements generic LifecycleEvidence.

## Critical open questions

1. Which device family should be the MVP reference implementation?
2. Is GARD allowed to connect directly to network devices in v1?
3. Does v1 execute commands, or only generate validated procedures?
4. Which system is authoritative for current firmware: CSV discovery, NetBox custom fields, ACS, or device polling?
5. Where should firmware packages be stored in production?
6. What RBAC model is required?
7. What approval model is required before an uplift wave can run?
8. Should maintenance windows be internal objects in GARD or external references to ITSM/change systems?
9. Should vulnerability intelligence be manual in v1 and automated in v2?
10. Which lifecycle fields, if any, should GARD write back to NetBox?

## Anti-goals

GARD is not:

- a replacement for NetBox
- a generic CMDB
- a monitoring system
- only a TFTP server
- only a firmware repository
- a TR-069 ACS replacement
- an uncontrolled autonomous upgrade engine
- a raw SQL/shell backend for AI agents

## Key principle

> GARD turns unknown lifecycle risk into visible, governed work.
