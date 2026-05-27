# GARD Native MCP Server

## Purpose

GARD shall include a native MCP server from v1 so approved AI agents, chatbots and operational copilots can safely query lifecycle state and create draft lifecycle work products.

Example clients:

- chatbot
- Netclaw
- operations copilot
- Cursor/IDE agent
- lifecycle assistant

## MCP Design Principle

MCP must expose curated lifecycle tools, not raw database, shell or network access.

Bad:

```text
agent -> SQL database
agent -> shell
agent -> unrestricted device command
```

Good:

```text
agent -> GARD MCP tool -> GARD API -> GARD policy/controller layer
```

## v1 MCP Tools

### Read-only tools

- `count_devices_outside_target`
- `list_devices_outside_target`
- `get_device_lifecycle_status`
- `get_target_firmware`
- `get_upgrade_path`
- `explain_blockers`
- `get_compliance_summary`
- `get_readiness_summary`
- `get_unknown_lifecycle_items`

### Reporting tools

- `create_readiness_report`
- `create_compliance_report`
- `create_blocker_summary`
- `create_vulnerability_priority_report`

### Draft-action tools

- `create_uplift_wave_draft`
- `create_exception_review_draft`

## Disallowed in v1 MCP

- execute firmware uplift
- approve wave
- approve exception
- change target firmware
- upload firmware package
- override blockers
- delete records
- run arbitrary commands
- query raw SQL

## Example Tool: count_devices_outside_target

Input:

```json
{
  "vendor": "Cisco",
  "model": "ISR1121",
  "region": "NO"
}
```

Output:

```json
{
  "vendor": "Cisco",
  "model": "ISR1121",
  "target_version": "17.12.4",
  "total_devices": 184,
  "outside_target": 63,
  "compliant": 121,
  "unknown_version": 4,
  "blocked": 11
}
```

## MCP Resources

Suggested resources:

```text
gard://schema/device
gard://schema/firmware-target
gard://schema/upgrade-path
gard://schema/prerequisite-rule
gard://schema/uplift-wave
gard://reports/compliance-summary
gard://reports/readiness-summary
gard://reports/blocked-devices
```

## MCP Security Requirements

- authentication required
- RBAC enforced
- tool-specific permissions
- audit every call
- schema-validate all inputs
- bounded/paginated outputs
- redact sensitive fields by default
- no raw infrastructure access
- write/draft tools require explicit permission
- execution tools are out of scope for v1

## Audit Fields

```yaml
McpToolCall:
  id: uuid
  timestamp: datetime
  mcp_client_id: string
  user_identity: string
  tool_name: string
  input_parameters: json
  authorization_result: string
  execution_result: string
  records_returned: integer
  action_created: string
  approval_required: boolean
  correlation_id: string
```
