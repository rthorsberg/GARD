"""Pydantic models for the F5 uplift REST API.

Mirrors ``specs/005-uplift-planning-waves/contracts/rest-openapi.yaml``
1:1. Every model uses ``extra='forbid'`` so unexpected fields trip the
contract test rather than silently shipping.

Slice 5b covers plans + waves; the exception models live here too (used
by the 5c router) so the schema surface lands in one place.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WaveState = Literal["draft", "submitted", "approved", "rejected", "cancelled", "invalidated"]
ExceptionState = Literal["pending_review", "approved", "rejected", "expired", "withdrawn"]
WaveDraftMode = Literal["strict", "skip_ineligible"]
SyntheticBlockerKind = Literal["missing_upgrade_path", "missing_observation_field"]


# ---- requests ------------------------------------------------------------


class CreatePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=8000)


class CreateWaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    target_version: str = Field(min_length=1, max_length=64)
    target_platform_family: str = Field(min_length=1, max_length=64)
    scope_selector: dict[str, Any]
    mode: WaveDraftMode = "strict"
    change_window_start: dt.datetime
    change_window_end: dt.datetime


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation: str = Field(min_length=20, max_length=2000)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation: str = Field(min_length=20, max_length=2000)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=500)


class CreateExceptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    blocker_rule_id: uuid.UUID | None = None
    synthetic_kind: SyntheticBlockerKind | None = None
    justification: str = Field(min_length=20, max_length=2000)
    expires_at: dt.datetime


# ---- responses -----------------------------------------------------------


class PlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str | None = None
    created_by: str
    created_at: dt.datetime
    archived_at: dt.datetime | None = None
    archived_by: str | None = None
    wave_count: int = Field(ge=0)
    correlation_id: str


class WaveDeviceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    hostname: str
    position: int = Field(ge=1)
    snapshot_target_version: str | None = None
    snapshot_observed_version: str | None = None
    readiness_evaluation_ref: str | None = None


class SkippedDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    reason: str
    current_readiness_state: str | None = None


class WaveEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    plan_id: str
    name: str
    state: WaveState
    target_version: str
    target_platform_family: str
    change_window_start: dt.datetime
    change_window_end: dt.datetime
    drafted_by: str
    drafted_at: dt.datetime
    submitted_by: str | None = None
    submitted_at: dt.datetime | None = None
    approved_by: str | None = None
    approved_at: dt.datetime | None = None
    approval_citation: str | None = None
    rejected_by: str | None = None
    rejected_at: dt.datetime | None = None
    rejection_citation: str | None = None
    cancelled_by: str | None = None
    cancelled_at: dt.datetime | None = None
    cancellation_reason: str | None = None
    invalidated_at: dt.datetime | None = None
    invalidated_reason: str | None = None
    device_count: int = Field(ge=0)
    devices: list[WaveDeviceRow] = Field(default_factory=list)
    skipped: list[SkippedDevice] = Field(default_factory=list)
    correlation_id: str


class ExceptionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    device_id: str
    blocker_rule_id: str | None = None
    synthetic_kind: str | None = None
    justification: str
    state: ExceptionState
    filed_by: str
    filed_at: dt.datetime
    approved_by: str | None = None
    approved_at: dt.datetime | None = None
    rejected_by: str | None = None
    rejected_at: dt.datetime | None = None
    withdrawn_by: str | None = None
    withdrawn_at: dt.datetime | None = None
    expires_at: dt.datetime
    expired_at: dt.datetime | None = None
    correlation_id: str


class PlanList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanEnvelope]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None


class WaveList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WaveEnvelope]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None


class ExceptionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExceptionEnvelope]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None


# ---- error envelope ------------------------------------------------------


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
