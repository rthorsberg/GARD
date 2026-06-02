"""Domain enums shared by ORM, Pydantic, and Alembic."""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any


def values_callable(enum_cls: type[enum.Enum]) -> Callable[[type[enum.Enum]], list[Any]]:
    """SQLAlchemy ``values_callable`` factory: serialize enums by ``.value``.

    Without this, ``Enum(MyEnum, native_enum=False)`` stores the
    member's *name*, which collides with our DB CHECK constraints that
    enforce the value strings. Use as
    ``Enum(MyEnum, values_callable=values_callable(MyEnum), ...)``.
    """

    def _by_value(_: type[enum.Enum]) -> list[Any]:
        return [m.value for m in enum_cls]

    return _by_value


class LifecycleState(enum.StrEnum):
    imported = "imported"
    classified = "classified"
    # Reserved for later features so the enum doesn't churn:
    target_defined = "target_defined"
    compliant = "compliant"
    outside_target = "outside_target"
    # F2: target matched but no observed_firmware on file (terminal until
    # next observation arrives). See spec.md FR-010 / FR-013 and
    # migration 0004.
    unknown = "unknown"
    ready_for_uplift = "ready_for_uplift"
    blocked = "blocked"
    uplift_planned = "uplift_planned"
    approval_pending = "approval_pending"
    approved = "approved"
    exception_approved = "exception_approved"


class Confidence(enum.StrEnum):
    exact = "exact"
    high = "high"
    medium = "medium"
    low = "low"
    manual_review_required = "manual_review_required"


class RuleSource(enum.StrEnum):
    file = "file"
    db = "db"


class ImportStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ActorType(enum.StrEnum):
    user = "user"
    system = "system"
    mcp_client = "mcp_client"
    adapter = "adapter"


class AuditResult(enum.StrEnum):
    success = "success"
    failure = "failure"
    denied = "denied"


class EvidenceType(enum.StrEnum):
    import_event = "import"
    manual_mapping = "manual_mapping"
    rule_override = "rule_override"
    re_evaluation = "re_evaluation"
    # F2: chain-of-custody record for a firmware blob upload. Carries the
    # computed sha256, byte count, and storage path so a future restore
    # can re-verify the artefact against the package row's declared sha.
    firmware_package_upload = "firmware_package_upload"
    # F2 (T059): one row per firmware-catalog reload pass. The
    # `source_checksum` is the Merkle-style SHA-256 over the sorted list
    # of loaded git SHAs, so a later auditor can confirm "this DB state
    # came from exactly these N files at exactly these commits".
    firmware_catalog_load = "firmware_catalog_load"
    # F7: chain-of-custody record for a NetBox sync run.
    netbox_sync = "netbox_sync"
    # F12: chain-of-custody record for an IPAM alignment run.
    netbox_ipam_alignment = "netbox_ipam_alignment"


class NetboxSyncRunStatus(enum.StrEnum):
    """F7 NetBox sync run lifecycle."""

    running = "running"
    completed = "completed"
    failed = "failed"


class IpamAlignmentRunStatus(enum.StrEnum):
    """F12 IPAM alignment run lifecycle."""

    completed = "completed"
    partial = "partial"
    failed = "failed"
    skipped = "skipped"


class AlignmentFindingSeverity(enum.StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class AlignmentFindingStatus(enum.StrEnum):
    open = "open"
    passed = "pass"

    @classmethod
    def from_value(cls, value: str) -> AlignmentFindingStatus:
        if value == "pass":
            return cls.passed
        return cls(value)


class AlignmentFindingKind(enum.StrEnum):
    """Closed enum — must match specs/012-netbox-ipam-dcim-align/contracts/finding-kinds.yaml."""

    mgmt_ip_match = "mgmt_ip_match"
    mgmt_ip_mismatch = "mgmt_ip_mismatch"
    mgmt_ip_missing_in_netbox = "mgmt_ip_missing_in_netbox"
    mgmt_ip_missing_in_gard = "mgmt_ip_missing_in_gard"
    mgmt_ip_ambiguous = "mgmt_ip_ambiguous"
    mgmt_ip_fallback_used = "mgmt_ip_fallback_used"
    interface_ip_bound = "interface_ip_bound"
    interface_missing_address = "interface_missing_address"
    prefix_vrf_scope_mismatch = "prefix_vrf_scope_mismatch"
    cross_device_address_conflict = "cross_device_address_conflict"
    shared_address = "shared_address"
    vrf_mismatch = "vrf_mismatch"
    vrf_orphaned_in_site = "vrf_orphaned_in_site"
    access_vlan_missing = "access_vlan_missing"
    vlan_out_of_scope = "vlan_out_of_scope"
    vlan_aligned = "vlan_aligned"
    overlay_rt_aligned = "overlay_rt_aligned"
    rt_missing_on_interface = "rt_missing_on_interface"
    rt_import_missing = "rt_import_missing"
    rt_export_missing = "rt_export_missing"
    l2vpn_module_unavailable = "l2vpn_module_unavailable"


class Role(enum.StrEnum):
    viewer = "viewer"
    lifecycle_manager = "lifecycle_manager"
    mcp_client = "mcp_client"
    system_admin = "system_admin"
    # F5: pure-approval authority. An org may want change-management
    # approvers who can sign off on uplift waves and exceptions WITHOUT
    # also getting DB-superuser-equivalent permissions (token mgmt,
    # MCP tool registration, etc.) that system_admin carries.
    change_approver = "change_approver"


class WaveState(enum.StrEnum):
    """F5 uplift-wave lifecycle (ADR-0016 §A)."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    invalidated = "invalidated"


class ExceptionState(enum.StrEnum):
    """F5 exception lifecycle (ADR-0016 §C)."""

    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    withdrawn = "withdrawn"
