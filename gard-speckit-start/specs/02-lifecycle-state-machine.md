# GARD Lifecycle State Machine

## Device Lifecycle States

```text
unknown
imported
classified
target_defined
compliant
outside_target
ready_for_uplift
blocked
uplift_planned
approval_pending
approved
uplift_queued
uplift_in_progress
uplift_completed
validated
failed
rollback_required
exception_approved
retirement_candidate
retired
```

## State Definitions

### unknown
GARD has insufficient data to classify the device.

### imported
Device was received from CSV/API/import source.

### classified
Vendor, model and platform have been normalized.

### target_defined
GARD found an applicable FirmwareTarget.

### compliant
Observed firmware matches target or an approved acceptable version.

### outside_target
Observed firmware does not match target.

### ready_for_uplift
Device is non-compliant but passes all blocking prerequisite checks.

### blocked
Device cannot be uplifted because one or more blocking prerequisites are not met.

### uplift_planned
Device is included in a dry-run uplift plan.

### approval_pending
Uplift plan or wave requires human/change approval.

### approved
Plan/wave has been approved for execution.

### uplift_queued
Execution is scheduled or queued.

### uplift_in_progress
Execution is active or manual workflow is being performed.

### uplift_completed
Execution completed; post-check validation may still be pending.

### validated
Post-check confirms target state and health requirements.

### failed
Uplift failed without immediate rollback requirement.

### rollback_required
Uplift failed or validation failed and rollback is required.

### exception_approved
Known non-compliance is accepted for a limited time with owner and approval.

### retirement_candidate
Device cannot reasonably be uplifted and should be replaced/retired.

### retired
Device is no longer active in lifecycle scope.

## Core Flow

```text
imported
  -> classified
  -> target_defined
  -> compliant

imported
  -> classified
  -> target_defined
  -> outside_target
  -> ready_for_uplift
  -> uplift_planned
  -> approval_pending
  -> approved
  -> uplift_queued
  -> uplift_in_progress
  -> uplift_completed
  -> validated

outside_target
  -> blocked
  -> ready_for_uplift

blocked
  -> exception_approved

blocked
  -> retirement_candidate
```

## Drift Taxonomy

GARD shall classify lifecycle drift instead of only saying compliant/non-compliant.

```text
target_drift
  Device not on target version.

catalog_drift
  Device model has no target firmware definition.

package_drift
  Target exists but firmware package is missing or unapproved.

rule_drift
  Target exists but upgrade path or prerequisites are undefined.

evidence_drift
  Device appears uplifted but no validation/evidence exists.

discovery_drift
  Actual state observation is stale.

exception_drift
  Exception has expired or lacks owner/approval.
```

## Required State Invariants

1. A device cannot become `ready_for_uplift` without a target and upgrade path.
2. A device cannot become `approved` without passing admission control.
3. A device cannot become `validated` without post-check evidence.
4. A device cannot enter two active uplift waves at the same time.
5. An exception must have owner, approver, reason and expiry date.
6. An expired exception returns to non-compliant/blocked state.
