"""Response/request models for the F3 compliance API.

Schemas mirror ``specs/003-compliance-drift-evaluation/contracts/
rest-openapi.yaml`` 1:1. Every model uses ``extra='forbid'`` so an
unexpected field on either input or output trips the test suite
rather than silently shipping.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DriftType = Literal[
    "target_drift",
    "catalog_drift",
    "package_drift",
    "rule_drift",
    "evidence_drift",
    "discovery_drift",
    "exception_drift",
]

ComplianceState = Literal[
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "unknown",
]

ReasonKind = Literal[
    "target_matched",
    "target_runner_up",
    "version_match",
    "version_mismatch",
    "missing_observation",
    "no_target_matched",
    "empty_catalog",
    "predicate_deferred",
    "stale_observation",
    "missing_upgrade_path",
    "package_not_built",
    # F5: surfaced via F4 → F3-shaped reasons when an exception is
    # the reason for `not_applicable`.
    "active_exception",
]

RecommendedActionKind = Literal[
    "upgrade_path_query",
    "define_target",
    "define_upgrade_path",
    "upload_firmware_package",
    "trigger_discovery",
    "request_observation_refresh",
    "escalate_to_catalog_owner",
    "acknowledge_exception",
]


class ReasonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReasonKind
    ref_type: str | None = None
    ref_id: str | None = None
    detail: str | None = None


class RecommendedActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RecommendedActionKind
    target_version: str | None = None
    target_platform_family: str | None = None
    target_device_id: str | None = None
    target_observation_id: str | None = None
    target_firmware_target_id: str | None = None
    requires: list[str] = Field(default_factory=list)
    detail: str | None = None


class ComplianceEnvelopeModel(BaseModel):
    """Full F3 envelope (REST response payload)."""

    model_config = ConfigDict(extra="forbid")

    state: ComplianceState
    summary: str
    drift_type: DriftType | None = None
    secondary_drift_types: list[DriftType] = Field(default_factory=list)
    target_ref: str | None = None
    target_version: str | None = None
    observed_version: str | None = None
    observation_ref: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    reasons: list[ReasonModel] = Field(default_factory=list)
    recommended_actions: list[RecommendedActionModel] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evaluation_id: str | None = None
    evaluated_at: dt.datetime
    correlation_id: str | None = None


class DriftCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_drift: int = 0
    catalog_drift: int = 0
    package_drift: int = 0
    rule_drift: int = 0
    evidence_drift: int = 0
    discovery_drift: int = 0
    exception_drift: int = 0


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_evaluated: int = Field(ge=0)
    compliant_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    counts_by_drift_type: DriftCounts
    filters_applied: dict[str, str] = Field(default_factory=dict)
    as_of: dt.datetime


class ComplianceDeviceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    hostname: str
    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    envelope: ComplianceEnvelopeModel


class ComplianceDeviceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ComplianceDeviceRow]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None


class EvaluateRequest(BaseModel):
    """POST /api/v1/compliance/evaluate body.

    Exactly one of ``device_ids`` or ``scope_selector`` MUST be set
    (OpenAPI ``oneOf``). Caller-validated; the endpoint also enforces
    via the ``model_validator`` below to keep error envelopes uniform.
    """

    model_config = ConfigDict(extra="forbid")

    device_ids: list[uuid.UUID] | None = Field(default=None, max_length=5000)
    scope_selector: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> EvaluateRequest:
        if (self.device_ids is None) == (self.scope_selector is None):
            raise ValueError(
                "EvaluateRequest requires exactly one of `device_ids` or `scope_selector`"
            )
        if self.device_ids is not None and len(self.device_ids) == 0:
            raise ValueError("device_ids must contain at least one id")
        return self


class EvaluateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_count: int = Field(ge=0)
    evaluated_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    correlation_id: str
