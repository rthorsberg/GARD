# GARD MVP Scope

## MVP Goal

Upload a device CSV and immediately allow humans, APIs and AI agents to ask:

- What is compliant?
- What is outside target?
- What is unknown?
- What is blocked?
- What is ready for uplift?
- What uplift plan would make devices compliant?

## MVP Includes

1. CSV import
2. Device lifecycle inventory
3. Device observations with freshness/confidence
4. Vendor/model/version normalization
5. Firmware target catalogue
6. Firmware package catalogue metadata
7. Upgrade path catalogue
8. Prerequisite rules
9. Compliance evaluation
10. Readiness evaluation
11. Drift classification
12. Dry-run uplift plan
13. Uplift wave draft creation
14. Guided workflow support
15. TFTP/FTP/HTTP file reference support
16. Command template library
17. Approval gates
18. Exception management
19. Audit logging
20. REST API
21. Native MCP server
22. Basic exportable reports
23. NetBox integration design
24. LifecycleEvidence records

## MVP Does Not Include

- full autonomous upgrades
- native discovery
- automatic CVE/NVD/CPE matching
- full SEGL certificate authority
- rich dependency graph
- deep ITSM integration
- full production-grade UI
- automatic rollback execution

## Reference MVP Device Family

The implementation team should select one or two device families for the first vertical slice, such as:

- Cisco ISR1121
- Cisco Catalyst 9300
- Zyxel NR5313
- Nokia 7750 SR

The first vertical slice must prove:

- import
- normalize
- target mapping
- drift detection
- readiness
- upgrade path
- package mapping
- dry-run plan
- wave creation
- MCP query
- evidence logging

## MVP Acceptance Criteria

1. A CSV can be imported with valid and invalid rows.
2. GARD produces import summary and error report.
3. Devices are normalized to canonical vendor/model/platform entities.
4. Target firmware can be defined for the reference model.
5. Devices are classified as compliant, outside target, unknown, blocked or ready.
6. GARD can produce a dry-run uplift plan.
7. GARD can create a draft wave.
8. MCP can answer: “How many Cisco ISR1121 are outside target version?”
9. Audit events are recorded.
10. LifecycleEvidence records are created for import/evaluation/planning.
