"""Pydantic models for the F4 readiness REST API.

Mirrors ``specs/004-readiness-prerequisites/contracts/rest-openapi.yaml``
1:1. Every model uses ``extra='forbid'`` so unexpected fields trip the
test suite rather than silently shipping.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReadinessState = Literal["ready_for_uplift", "blocked", "not_applicable"]

BlockerSeverity = Literal["required", "recommended"]

BlockerPredicateKind = Literal[
    "min_ram_mb",
    "min_disk_mb",
    "min_current_version",
    "hardware_revision_in",
    "license_present",
    "intermediate_version_required",
    "not_in_state",
    "region_in",
    "tagged_with",
    "missing_upgrade_path",
    "missing_observation_field",
]

RecommendedActionKind = Literal[
    # F3 vocabulary:
    "upgrade_path_query",
    "define_target",
    "define_upgrade_path",
    "upload_firmware_package",
    "trigger_discovery",
    "request_observation_refresh",
    "escalate_to_catalog_owner",
    "acknowledge_exception",
    # F4 additions (data-model.md §2.4):
    "schedule_uplift_wave",
    "hardware_refresh",
    "license_acquire",
    "firmware_intermediate_step",
    "import_observation",
    # F5 (uplift planning & waves) additions (data-model.md §2.4):
    "submit_for_approval",
    "assign_approver",
    "extend_change_window",
    "request_exception_review",
    "cancel_wave",
]

ReasonKind = Literal[
    # Carried over from F3 — F4 reuses for not_applicable carve-outs:
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
    # F5: surfaced when an approved-and-active exception flips the
    # readiness verdict to `not_applicable` (ADR-0016 §C).
    "active_exception",
]


class BlockerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    rule_name: str | None = None
    predicate_kind: BlockerPredicateKind
    severity: BlockerSeverity
    required: dict[str, Any] | None = None
    observed: dict[str, Any] | None = None
    detail: str


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


class ReasonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReasonKind
    ref_type: str | None = None
    ref_id: str | None = None
    detail: str | None = None


class ReadinessEnvelopeModel(BaseModel):
    """Full F4 envelope (REST response payload)."""

    model_config = ConfigDict(extra="forbid")

    state: ReadinessState
    summary: str
    target_version: str | None = None
    observed_version: str | None = None
    upgrade_path_exists: bool = False
    applicable_rules_count: int = Field(default=0, ge=0)
    blockers: list[BlockerModel] = Field(default_factory=list)
    recommended_actions: list[RecommendedActionModel] = Field(default_factory=list)
    reasons: list[ReasonModel] = Field(default_factory=list)
    compliance_evaluation_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evaluation_id: str | None = None
    evaluated_at: dt.datetime
    correlation_id: str | None = None


class BlockerCategoryCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate_kind: BlockerPredicateKind
    count: int = Field(ge=0)


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_outside_target: int = Field(ge=0)
    ready_for_uplift_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    not_applicable_count: int = Field(ge=0)
    top_blocker_categories: list[BlockerCategoryCount] = Field(default_factory=list, max_length=10)
    filters_applied: dict[str, str] = Field(default_factory=dict)
    as_of: dt.datetime
    correlation_id: str


class ReadinessDeviceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    hostname: str
    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    envelope: ReadinessEnvelopeModel


class ReadinessDeviceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReadinessDeviceRow]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None


class EvaluateRequest(BaseModel):
    """POST /api/v1/readiness/evaluate body.

    Exactly one of ``device_ids`` or ``scope_selector`` MUST be set.
    Mirrors F3's EvaluateRequest contract.
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
    not_applicable_count: int = Field(ge=0)
    correlation_id: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
