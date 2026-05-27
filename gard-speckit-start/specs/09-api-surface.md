# GARD API Surface Draft

## API Principles

- Versioned REST API.
- MCP server calls internal API/business services, not database directly.
- All write operations are audited.
- Long-running workflows return IDs and status endpoints.
- All list endpoints support filtering and pagination.

## API Domains

```text
/imports
/devices
/observations
/normalization
/firmware-targets
/firmware-packages
/upgrade-paths
/prerequisites
/compliance
/readiness
/plans
/waves
/workflows
/exceptions
/risk
/evidence
/audit
/mcp-admin
```

## Example Endpoints

### Import CSV

```http
POST /api/v1/imports/devices/csv
Content-Type: multipart/form-data
```

### List devices

```http
GET /api/v1/devices?vendor=Cisco&model=ISR1121&compliance_state=outside_target
```

### Evaluate device

```http
POST /api/v1/devices/{device_id}/evaluate
```

### Create dry-run plan

```http
POST /api/v1/plans
```

Payload:

```json
{
  "filter": {
    "vendor": "Cisco",
    "model": "ISR1121",
    "region": "NO"
  },
  "target_version": "17.12.4",
  "mode": "dry_run"
}
```

### Create wave draft

```http
POST /api/v1/waves
```

### Approve wave

```http
POST /api/v1/waves/{wave_id}/approve
```

### Get readiness summary

```http
GET /api/v1/readiness/summary?vendor=Cisco&model=ISR1121
```

### Get risk priority report

```http
GET /api/v1/risk/priority?vendor=Cisco&model=ISR1121
```

### Get audit events

```http
GET /api/v1/audit?object_type=UpliftWave&object_id={wave_id}
```

## Response Pattern

For explainable evaluations:

```json
{
  "state": "blocked",
  "summary": "Device is outside target and blocked by missing backup.",
  "facts": {},
  "reasons": [],
  "recommended_actions": [],
  "confidence": "high"
}
```
