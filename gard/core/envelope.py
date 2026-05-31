"""Explainable response envelope (ADR-0005)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from gard.core.logging import get_correlation_id
from gard.models import utcnow

EnvelopeState = Literal["known", "unknown", "conflicting", "stale", "classified", "imported"]
ReasonKind = Literal[
    "rule_match",
    "manual_mapping",
    "evidence_ref",
    "missing_input",
    "rule_conflict",
    "stale_observation",
    "policy_decision",
]


class Reason(BaseModel):
    kind: ReasonKind
    ref: str | None = None
    detail: str = ""


class ResponseEnvelope[T](BaseModel):
    state: EnvelopeState
    summary: str
    facts: T
    reasons: list[Reason] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: dt.datetime
    correlation_id: str | None = None


_CONFIDENCE_FROM_LEVEL: dict[str, float] = {
    "exact": 1.0,
    "high": 0.85,
    "medium": 0.6,
    "low": 0.3,
    "manual_review_required": 0.0,
}


def confidence_from_level(level: str) -> float:
    """Map the qualitative confidence enum to a numeric score (ADR-0005)."""
    return _CONFIDENCE_FROM_LEVEL.get(level, 0.0)


def build_envelope(
    *,
    state: EnvelopeState,
    summary: str,
    facts: Any,
    reasons: list[Reason] | None = None,
    recommended_actions: list[str] | None = None,
    confidence: float = 0.0,
    as_of: dt.datetime | None = None,
    correlation_id: str | None = None,
) -> ResponseEnvelope[Any]:
    """Construct a :class:`ResponseEnvelope` from positional inputs."""
    return ResponseEnvelope[Any](
        state=state,
        summary=summary,
        facts=facts,
        reasons=reasons or [],
        recommended_actions=recommended_actions or [],
        confidence=confidence,
        as_of=as_of or utcnow(),
        correlation_id=correlation_id or get_correlation_id(),
    )


# ---- F2: firmware-compliance envelope variant -------------------------
# A separate type (rather than a polymorphic extension of ResponseEnvelope)
# because F2's state space, reason taxonomy, and target-citation fields
# are domain-bound and the type system makes the boundary cleaner.

FirmwareComplianceState = Literal[
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "unknown",
]

FirmwareComplianceReasonKind = Literal[
    "target_matched",
    "target_runner_up",
    "version_match",
    "version_mismatch",
    "missing_observation",
    "no_target_matched",
    "empty_catalog",
    "predicate_deferred",
]


class FirmwareComplianceReason(BaseModel):
    kind: FirmwareComplianceReasonKind
    ref: str | None = None  # FirmwareTarget id for target_matched / target_runner_up
    detail: str | None = None


class FirmwareComplianceEnvelope(BaseModel):
    state: FirmwareComplianceState
    summary: str
    target_ref: str | None = None
    target_version: str | None = None
    observed_version: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    reasons: list[FirmwareComplianceReason] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)  # always [] in F2
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    as_of: dt.datetime
    correlation_id: str | None = None


def build_firmware_compliance_envelope(
    *,
    state: FirmwareComplianceState,
    summary: str,
    target_ref: str | None = None,
    target_version: str | None = None,
    observed_version: str | None = None,
    facts: dict[str, Any] | None = None,
    reasons: list[FirmwareComplianceReason] | None = None,
    confidence: float = 1.0,
    as_of: dt.datetime | None = None,
    correlation_id: str | None = None,
) -> FirmwareComplianceEnvelope:
    """Construct a :class:`FirmwareComplianceEnvelope` from positional inputs."""
    return FirmwareComplianceEnvelope(
        state=state,
        summary=summary,
        target_ref=target_ref,
        target_version=target_version,
        observed_version=observed_version,
        facts=facts or {},
        reasons=reasons or [],
        recommended_actions=[],  # F3 will populate; F2 keeps empty.
        confidence=confidence,
        as_of=as_of or utcnow(),
        correlation_id=correlation_id or get_correlation_id(),
    )


# ---- F3: compliance envelope variant ----------------------------------
# F3 extends F2's envelope with categorical drift typing and a typed
# recommended-actions vocabulary (ADR-0014). The F2 envelope stays valid
# for callers that only want target/observed; the F3 envelope is the
# super-set surface used by /devices/{id}/compliance and the MCP
# `get_compliance_summary` tool.

DriftType = Literal[
    "target_drift",
    "catalog_drift",
    "package_drift",
    "rule_drift",
    "evidence_drift",
    "discovery_drift",
    "exception_drift",
]

ComplianceReasonKind = Literal[
    # inherited verbatim from F2:
    "target_matched",
    "target_runner_up",
    "version_match",
    "version_mismatch",
    "missing_observation",
    "no_target_matched",
    "empty_catalog",
    "predicate_deferred",
    # new in F3:
    "stale_observation",
    "missing_upgrade_path",
    "package_not_built",
]

RecommendedActionKind = Literal[
    "upgrade_path_query",
    "define_target",
    "define_upgrade_path",
    "upload_firmware_package",
    "trigger_discovery",
    "request_observation_refresh",
    "escalate_to_catalog_owner",
    # Reserved for F5 — F3 will never emit this; contract surface only.
    "acknowledge_exception",
    # F4 (readiness & prerequisites) additions — see ADR-0015.
    "schedule_uplift_wave",
    "hardware_refresh",
    "license_acquire",
    "firmware_intermediate_step",
    "import_observation",
]


class ComplianceReason(BaseModel):
    """Extended reason for F3 — superset of F2's reason kinds."""

    kind: ComplianceReasonKind
    ref_type: str | None = None  # e.g., "FirmwareTarget", "FirmwarePackage"
    ref_id: str | None = None
    detail: str | None = None


class RecommendedAction(BaseModel):
    """Typed action operators or upstream tools can take.

    F3 emits actions with the minimum payload needed to route work
    (which catalog file, which platform). The `requires` list names
    permission strings the actor must hold to execute — viewers see
    suggestions, lifecycle managers see actionable buttons.
    """

    kind: RecommendedActionKind
    target_version: str | None = None
    target_platform_family: str | None = None
    target_device_id: str | None = None
    target_observation_id: str | None = None
    target_firmware_target_id: str | None = None
    requires: list[str] = Field(default_factory=list)
    detail: str | None = None


class ComplianceEnvelope(BaseModel):
    """F3 compliance envelope — F2 super-set with typed drift + actions."""

    state: FirmwareComplianceState
    summary: str
    drift_type: DriftType | None = None
    secondary_drift_types: list[DriftType] = Field(default_factory=list)
    target_ref: str | None = None
    target_version: str | None = None
    observed_version: str | None = None
    observation_ref: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    reasons: list[ComplianceReason] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evaluation_id: str | None = None
    evaluated_at: dt.datetime
    correlation_id: str | None = None


def build_compliance_envelope(
    *,
    state: FirmwareComplianceState,
    summary: str,
    drift_type: DriftType | None = None,
    secondary_drift_types: list[DriftType] | None = None,
    target_ref: str | None = None,
    target_version: str | None = None,
    observed_version: str | None = None,
    observation_ref: str | None = None,
    facts: dict[str, Any] | None = None,
    reasons: list[ComplianceReason] | None = None,
    recommended_actions: list[RecommendedAction] | None = None,
    confidence: float = 1.0,
    evaluation_id: str | None = None,
    evaluated_at: dt.datetime | None = None,
    correlation_id: str | None = None,
) -> ComplianceEnvelope:
    """Construct a :class:`ComplianceEnvelope` from positional inputs."""
    return ComplianceEnvelope(
        state=state,
        summary=summary,
        drift_type=drift_type,
        secondary_drift_types=secondary_drift_types or [],
        target_ref=target_ref,
        target_version=target_version,
        observed_version=observed_version,
        observation_ref=observation_ref,
        facts=facts or {},
        reasons=reasons or [],
        recommended_actions=recommended_actions or [],
        confidence=confidence,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at or utcnow(),
        correlation_id=correlation_id or get_correlation_id(),
    )


# ---- F4: readiness envelope -------------------------------------------
# Bridges F3's drift verdict and F5's uplift-wave planner: which
# `outside_target` devices are SAFE to schedule and which are blocked,
# with each blocker citing a specific F2 rule (or a closed-enum
# synthetic kind). See ADR-0015 for the precedence/ordering rules.

ReadinessState = Literal[
    "ready_for_uplift",
    "blocked",
    "not_applicable",
]

BlockerPredicateKind = Literal[
    # Inherited verbatim from F2's PredicateKind enum:
    "min_ram_mb",
    "min_disk_mb",
    "min_current_version",
    "hardware_revision_in",
    "license_present",
    "intermediate_version_required",
    "not_in_state",
    "region_in",
    "tagged_with",
    # F4 synthetic kinds — not in F2's catalogue:
    "missing_upgrade_path",
    "missing_observation_field",
]

BlockerSeverity = Literal["required", "recommended"]

# `not_applicable` carve-out reason kinds. The per-device endpoint's
# `reasons[]` array carries exactly one of these on a not_applicable
# verdict; the summary endpoint uses them for stale-input skipping.
ReadinessNotApplicableReason = Literal[
    "already_compliant",
    "no_target_resolved",
    "no_observation_to_verify",
    "lifecycle_unknown",
    "no_compliance_evaluation",
    "stale_compliance_input",
]


class Blocker(BaseModel):
    """One failed prerequisite (or synthetic equivalent) for a device.

    `rule_id` is null for synthetic blockers (`missing_upgrade_path`,
    `missing_observation_field`); non-null when the blocker comes from
    an evaluated F2 `FirmwarePrerequisiteRule`. `required` and
    `observed` carry predicate-kind-specific JSON payloads — operators
    can read the `detail` string; tooling parses the structured pair.
    """

    rule_id: str | None = None
    rule_name: str | None = None
    predicate_kind: BlockerPredicateKind
    severity: BlockerSeverity
    required: dict[str, Any] | None = None
    observed: dict[str, Any] | None = None
    detail: str


class ReadinessEnvelope(BaseModel):
    """F4 readiness envelope — sibling of `ComplianceEnvelope`."""

    state: ReadinessState
    summary: str
    target_version: str | None = None
    observed_version: str | None = None
    upgrade_path_exists: bool = False
    applicable_rules_count: int = Field(default=0, ge=0)
    blockers: list[Blocker] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    reasons: list[ComplianceReason] = Field(default_factory=list)
    compliance_evaluation_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evaluation_id: str | None = None
    evaluated_at: dt.datetime
    correlation_id: str | None = None


def build_readiness_envelope(
    *,
    state: ReadinessState,
    summary: str,
    target_version: str | None = None,
    observed_version: str | None = None,
    upgrade_path_exists: bool = False,
    applicable_rules_count: int = 0,
    blockers: list[Blocker] | None = None,
    recommended_actions: list[RecommendedAction] | None = None,
    reasons: list[ComplianceReason] | None = None,
    compliance_evaluation_ref: str | None = None,
    confidence: float = 1.0,
    evaluation_id: str | None = None,
    evaluated_at: dt.datetime | None = None,
    correlation_id: str | None = None,
) -> ReadinessEnvelope:
    """Construct a :class:`ReadinessEnvelope` from positional inputs."""
    return ReadinessEnvelope(
        state=state,
        summary=summary,
        target_version=target_version,
        observed_version=observed_version,
        upgrade_path_exists=upgrade_path_exists,
        applicable_rules_count=applicable_rules_count,
        blockers=blockers or [],
        recommended_actions=recommended_actions or [],
        reasons=reasons or [],
        compliance_evaluation_ref=compliance_evaluation_ref,
        confidence=confidence,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at or utcnow(),
        correlation_id=correlation_id or get_correlation_id(),
    )
