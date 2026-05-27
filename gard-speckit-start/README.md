# GARD Speckit Start Package

This package contains background documents for turning **GARD** into a formal specification using a Speckit-style workflow: constitution, specification, implementation plan, tasks, and ADRs.

GARD is an MCP-native firmware/software lifecycle governance platform for Communication Service Provider (CSP) network infrastructure.

## Recommended Speckit processing order

1. `context/00-product-brief.md`
2. `context/01-domain-assumptions.md`
3. `specs/00-prd-gard.md`
4. `specs/01-domain-model.md`
5. `specs/02-lifecycle-state-machine.md`
6. `specs/03-architecture.md`
7. `specs/04-mvp-scope.md`
8. `specs/05-netbox-tr069-positioning.md`
9. `specs/06-mcp-server.md`
10. `specs/07-risk-vulnerability.md`
11. `specs/08-security-rbac-audit.md`
12. `specs/09-api-surface.md`
13. `adr/ADR-0001-standalone-platform-with-netbox-integration.md`
14. `adr/ADR-0002-governance-first-not-autonomous-upgrade.md`
15. `adr/ADR-0003-mcp-native-from-v1.md`
16. `adr/ADR-0004-lifecycle-as-code.md`
17. `adr/ADR-0005-tr069-as-southbound-adapter.md`
18. `examples/`

## Key baseline statement

> GARD is an MCP-native firmware lifecycle governance platform for CSP networks. It reconciles observed device software state against approved target state, calculates drift, risk and readiness, plans controlled uplift waves, integrates with execution systems such as TR-069, CLI, NETCONF and NSO, and records lifecycle evidence for every critical change.

## Important product boundary

GARD is **not** just a firmware upgrade script. It is the lifecycle brain that governs firmware/software state.

- NetBox is the source of infrastructure reference.
- GARD owns firmware lifecycle policy, readiness, risk, uplift planning and lifecycle evidence.
- TR-069/ACS, NETCONF, CLI, NSO, Ansible/Nornir and vendor APIs are execution adapters.
- MCP exposes safe, curated lifecycle tools to approved AI agents.
- SEGL is a future evidence/certificate layer; GARD v1 should create structured LifecycleEvidence records.
