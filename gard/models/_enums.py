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


class Role(enum.StrEnum):
    viewer = "viewer"
    lifecycle_manager = "lifecycle_manager"
    mcp_client = "mcp_client"
    system_admin = "system_admin"
