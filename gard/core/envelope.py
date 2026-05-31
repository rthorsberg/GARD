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
