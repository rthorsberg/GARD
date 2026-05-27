# GARD Domain Model

## Core Entities

### Device

A network element known to GARD for lifecycle purposes.

Fields:

```yaml
Device:
  id: uuid
  hostname: string
  management_ip: string
  vendor_raw: string
  vendor_normalized: string
  model_raw: string
  model_normalized: string
  platform_family: string
  hardware_revision: string
  serial_number: string
  site: string
  region: string
  role: string
  source_system: string
  lifecycle_state: string
  compliance_state: string
  readiness_state: string
  risk_score: integer
  created_at: datetime
  updated_at: datetime
```

### DeviceObservation

Actual state observed from CSV, discovery, ACS, NetBox, CLI, NETCONF or another source.

```yaml
DeviceObservation:
  id: uuid
  device_id: uuid
  observed_firmware: string
  observed_bootloader: string
  observed_hardware_revision: string
  observed_at: datetime
  observed_by: string
  confidence: enum[exact, high, medium, low, manual_review_required]
  raw_payload: json
```

Key principle:

> Actual firmware state is a time-bound observation, not permanent truth.

### FirmwareTarget

Approved desired state for a device category.

```yaml
FirmwareTarget:
  id: uuid
  vendor: string
  model: string
  platform_family: string
  hardware_revision: string
  role: string
  region: string
  target_version: string
  approved_versions: list
  deprecated_versions: list
  blocked_versions: list
  valid_from: date
  valid_until: date
  owner: string
  status: enum[draft, approved, deprecated, retired]
```

### FirmwarePackage

Metadata about a package/image used for uplift.

```yaml
FirmwarePackage:
  id: uuid
  vendor: string
  model: string
  platform_family: string
  version: string
  filename: string
  storage_uri: string
  checksum_sha256: string
  checksum_verified: boolean
  file_size: integer
  supported_protocols: list[tftp, ftp, http]
  preferred_protocol: enum[http, ftp, tftp]
  approval_status: enum[draft, uploaded, checksum_verified, approved, deprecated, blocked]
```

### UpgradePath

Allowed movement from one version state to another.

```yaml
UpgradePath:
  id: uuid
  vendor: string
  model: string
  from_version_pattern: string
  to_version: string
  intermediate_versions: list
  required_packages: list
  known_bad_paths: list
  notes: string
```

### PrerequisiteRule

Condition required before uplift.

```yaml
PrerequisiteRule:
  id: uuid
  vendor: string
  model: string
  target_version: string
  rule_type: string
  rule_value: json
  severity: enum[info, warning, blocking, critical]
  blocking: boolean
  description: string
```

### ComplianceEvaluation

Result of comparing actual state to target state.

```yaml
ComplianceEvaluation:
  id: uuid
  device_id: uuid
  observed_version: string
  target_version: string
  compliance_state: enum[compliant, outside_target, approved_but_not_target, deprecated, blocked_version, unknown_version, target_missing, upgrade_path_missing]
  drift_type: string
  explanation: string
  evaluated_at: datetime
```

### ReadinessEvaluation

Result of checking prerequisites.

```yaml
ReadinessEvaluation:
  id: uuid
  device_id: uuid
  readiness_state: enum[ready, not_ready, manual_review_required, unknown]
  blockers: list
  warnings: list
  evaluated_at: datetime
```

### UpliftPlan

Dry-run plan for making devices compliant.

```yaml
UpliftPlan:
  id: uuid
  device_ids: list
  target_version: string
  plan_status: enum[draft, ready, blocked, approved, expired]
  planned_steps: list
  blockers: list
  risk_summary: json
  created_by: string
  created_at: datetime
```

### UpliftWave

Batch of devices planned for uplift.

```yaml
UpliftWave:
  id: uuid
  name: string
  device_ids: list
  target_version: string
  status: enum[draft, pending_approval, approved, queued, in_progress, completed, failed, cancelled]
  max_concurrency: integer
  failure_threshold: integer
  maintenance_window_ref: string
```

### LifecycleEvidence

Structured proof of lifecycle events.

```yaml
LifecycleEvidence:
  id: uuid
  evidence_type: enum[import, evaluation, readiness, plan, approval, uplift_started, uplift_completed, validation, exception, retirement]
  subject_type: string
  subject_id: uuid
  before_state: json
  after_state: json
  actor: string
  system: string
  timestamp: datetime
  checksum: string
  references: list
```

### AuditEvent

Immutable log of action.

```yaml
AuditEvent:
  id: uuid
  timestamp: datetime
  actor: string
  action: string
  object_type: string
  object_id: uuid
  old_value: json
  new_value: json
  correlation_id: string
```
