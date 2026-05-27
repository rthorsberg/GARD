# GARD Architecture

## Architecture Style

GARD should use a controller-inspired architecture inspired by Terraform, Kubernetes, SDN controllers and network orchestrators.

Core concepts:

- desired state
- actual state
- drift
- plan
- approval
- apply
- verify
- evidence
- reconcile

## High-Level Architecture

```text
+------------------------------------------------------+
| UI / NetBox Plugin / REST Clients / MCP Clients      |
+---------------------------+--------------------------+
                            |
+---------------------------v--------------------------+
| GARD API Layer                                      |
| REST API | MCP Server | Auth | RBAC | Audit          |
+---------------------------+--------------------------+
                            |
+---------------------------v--------------------------+
| GARD Core Controllers                               |
| Import | Normalize | Target | Compliance | Risk      |
| Readiness | Planning | Wave | Evidence | Policy      |
+---------------------------+--------------------------+
                            |
+---------------------------v--------------------------+
| GARD Persistence                                    |
| PostgreSQL | Object/File Storage | Audit Log          |
+---------------------------+--------------------------+
                            |
+---------------------------v--------------------------+
| Southbound Adapters                                 |
| TFTP/FTP/HTTP | TR-069 | TR-369 | CLI | NETCONF      |
| NSO | Ansible/Nornir | Vendor APIs                  |
+------------------------------------------------------+
```

## Controller Responsibilities

### Import Controller
Processes CSV/API/imports and creates DeviceObservation records.

### Normalization Controller
Maps raw vendor/model/version values to canonical lifecycle entities.

### Target State Controller
Finds applicable FirmwareTarget for each device.

### Compliance Controller
Compares observed actual state against target state.

### Risk Controller
Maps vulnerability/advisory/support status to devices.

### Readiness Controller
Evaluates prerequisites.

### Planning Controller
Creates dry-run uplift plans.

### Wave Controller
Manages batch/wave planning, approval, queueing and state.

### Policy/Admission Controller
Prevents unsafe lifecycle actions from entering execution.

### Evidence Controller
Creates LifecycleEvidence records.

### MCP Controller
Exposes safe agent-facing lifecycle tools.

## Plan / Apply / Verify / Evidence

GARD should produce an explicit plan before any uplift.

```text
Plan:
  what will change, what will not change, blockers, risk, dependencies

Apply:
  guided or adapter-driven execution after approval

Verify:
  post-check confirms target version and health

Evidence:
  structured proof of before/after, approval, checksum and result
```

## Lifecycle-as-Code

GARD should support Git-managed catalogues.

```text
gard-catalog/
├── vendors/
│   └── cisco/
│       └── isr1121/
│           ├── target.yaml
│           ├── upgrade-paths.yaml
│           ├── prerequisites.yaml
│           └── commands.yaml
├── policies/
└── normalization/
```

## Deployment Recommendation

PoC/MVP:

- Docker Compose
- PostgreSQL
- Local filesystem/object storage for firmware metadata and files
- HTTP file server
- optional TFTP/FTP containers

Production direction:

- Kubernetes/OpenShift
- PostgreSQL HA
- object storage
- Vault/secret manager
- RBAC/SSO integration
- segmented southbound adapter network
