"""Domain enums shared by ORM, Pydantic, and Alembic."""

from __future__ import annotations

import enum


class LifecycleState(enum.StrEnum):
    imported = "imported"
    classified = "classified"
    # Reserved for later features so the enum doesn't churn:
    target_defined = "target_defined"
    compliant = "compliant"
    outside_target = "outside_target"
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


class Role(enum.StrEnum):
    viewer = "viewer"
    lifecycle_manager = "lifecycle_manager"
    mcp_client = "mcp_client"
    system_admin = "system_admin"
