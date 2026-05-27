# PRD: GARD — Firmware Lifecycle Governance Platform

## 1. Executive Summary

GARD is an MCP-native firmware/software lifecycle governance platform for Communication Service Provider network infrastructure.

It ingests observed device data, maps devices to approved target firmware/software versions, evaluates drift, risk and readiness, plans controlled uplift waves, integrates with execution systems, and records lifecycle evidence.

## 2. Problem Statement

CSP network estates contain routers, switches, CPE, access devices, BNGs, optical equipment and legacy platforms from many vendors. Firmware and software lifecycle is often fragmented across spreadsheets, vendor documents, manual procedures, ACS platforms, inventory records, and engineer knowledge.

This causes operational and security risk:

- unknown firmware versions
- unsupported firmware
- exposed vulnerabilities
- unclear upgrade paths
- missing prerequisites
- lack of upgrade evidence
- manual planning
- poor cross-domain governance

## 3. Product Vision

GARD shall become the firmware/software lifecycle control plane for CSP network infrastructure.

GARD shall answer:

- What firmware/software is each device running?
- What should it be running?
- What is the lifecycle drift?
- What risk does the drift represent?
- Is the device ready for uplift?
- What safe uplift plan is required?
- Which system should execute the uplift?
- What evidence proves the result?

## 4. Product Scope

### v1 Scope

- CSV import from discovery system
- Device lifecycle inventory
- Vendor/model/version normalization
- Firmware target catalogue
- Firmware package catalogue
- Upgrade path catalogue
- Prerequisite rule engine
- Compliance evaluation
- Readiness evaluation
- Drift classification
- Guided uplift planning
- Batch/wave planning
- TFTP/FTP/HTTP delivery references
- Command template library
- Approval gates
- Exception management
- Audit logging
- REST API
- Native MCP server
- NetBox integration design
- LifecycleEvidence records

### Later Scope

- Native discovery
- Full vendor advisory/CVE automation
- TR-069/USP adapter execution
- NETCONF/CLI/NSO/Ansible execution adapters
- Advanced dependency graph
- Full SEGL certificate integration
- Closed-loop continuous reconciliation
- Rich UI dashboards

## 5. Core Principles

1. Governance before execution.
2. Desired state and actual state must be separate.
3. Risk and readiness must be separate.
4. Unknown is a first-class lifecycle state.
5. All actions must be explainable.
6. Uplift requires approval.
7. MCP exposes curated tools, not raw infrastructure access.
8. GARD integrates with existing domain systems instead of replacing them.
9. Lifecycle catalogue should be manageable as code.
10. Evidence must be produced for critical lifecycle events.

## 6. Success Metrics

- Percentage of devices with known current firmware
- Percentage of devices mapped to target firmware
- Percentage of devices compliant with target firmware
- Number of devices with unknown target/version/path
- Number of devices ready for uplift
- Number of blocked devices with known blocker reason
- Number of successful uplift plans/waves
- Reduction in unsupported firmware
- Reduction in high-risk vulnerable devices
- Time from import to compliance report
- Time from compliance finding to uplift plan

## 7. Positioning

GARD is not a firmware upgrade script. It is a lifecycle governance platform.

Traditional upgrade tooling asks:

> How do I push this image to this device?

GARD asks:

> Should this device be upgraded, to what, through which path, under which prerequisites, with what risk, approved by whom, executed by which adapter, validated how, and evidenced where?
