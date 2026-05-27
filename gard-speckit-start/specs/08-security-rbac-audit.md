# Security, RBAC and Audit

## Security Principles

GARD interacts with sensitive lifecycle state and may eventually trigger network device changes. Security must be foundational.

Principles:

1. Least privilege.
2. No uncontrolled execution.
3. Explicit approval gates.
4. Full audit trail.
5. Secure credential handling.
6. Separation of read, plan, approve and execute permissions.
7. MCP exposes curated tools only.
8. Firmware files require integrity validation.

## Roles

Suggested roles:

```text
viewer
lifecycle_manager
network_engineer
firmware_admin
approver
security_reviewer
mcp_client
system_admin
```

## Permission Categories

```text
read_device_lifecycle
read_catalog
read_risk
import_devices
manage_targets
manage_packages
verify_checksum
manage_prerequisites
create_plan
create_wave_draft
approve_wave
execute_workflow
approve_exception
manage_mcp_tools
admin_system
```

## Approval Gates

Required before:

- firmware package approved
- target firmware changed to approved
- uplift wave approved
- high-risk exception approved
- blocker override
- production execution

## Credential Handling

If GARD connects to devices or adapters:

- no plain-text credentials in database
- integrate with Vault/secret manager
- per-adapter credentials
- credential use audited
- separate read-only and write credentials where possible
- restrict network access to southbound adapters

## Audit Events

GARD shall audit:

- CSV import
- normalization rule change
- target firmware change
- package upload
- checksum verification
- prerequisite rule change
- compliance evaluation
- readiness evaluation
- plan creation
- wave creation
- approval
- execution start
- execution result
- exception approval
- MCP call
- API write action

## Audit Event Fields

```yaml
AuditEvent:
  id: uuid
  timestamp: datetime
  actor: string
  actor_type: enum[user, system, mcp_client, adapter]
  action: string
  object_type: string
  object_id: string
  old_value: json
  new_value: json
  result: enum[success, failure, denied]
  correlation_id: string
  source_ip: string
```

## File Integrity

Firmware packages require:

- checksum metadata
- checksum verification
- approval state
- storage URI
- upload/approval audit

GARD should prevent unverified packages from being used in approved uplift waves unless explicit exception is granted.
