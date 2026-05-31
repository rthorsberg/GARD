"""MCP tool: create_exception_review_draft (R-9 read-shaped proposal)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.api.schemas.readiness import BlockerModel
from gard.core import readiness_evaluation_controller as readiness_ctrl
from gard.core import uplift_exception_controller as exc_ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.core.settings import get_settings
from gard.models import Device

TOOL_NAME = "create_exception_review_draft"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class CreateExceptionReviewDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    suggested_lifetime_days: int = Field(default=30, ge=1, le=365)


class CandidateBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocker_rule_id: uuid.UUID | None = None
    synthetic_kind: str | None = None
    predicate_kind: str
    severity: str
    detail: str


class CreateExceptionReviewDraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str | None = None
    candidate_blockers: list[CandidateBlocker] = Field(default_factory=list)
    suggested_expires_at: dt.datetime
    already_active_exception_id: uuid.UUID | None = None
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: CreateExceptionReviewDraftInput,
) -> CreateExceptionReviewDraftOutput:
    device = session.get(Device, body.device_id)
    hostname = device.hostname if device is not None else None
    settings = get_settings()
    lifetime = min(body.suggested_lifetime_days, settings.exception_max_lifetime_days)
    suggested_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(days=lifetime)

    active = exc_ctrl.find_active_approved_exception(session, body.device_id)
    row = readiness_ctrl.latest_evaluation_for(session, body.device_id)
    blockers: list[CandidateBlocker] = []
    if row is not None and row.readiness_state == "blocked":
        for raw in row.blockers or []:
            b = BlockerModel(**raw)
            blockers.append(
                CandidateBlocker(
                    blocker_rule_id=uuid.UUID(b.rule_id) if b.rule_id else None,
                    synthetic_kind=b.predicate_kind
                    if b.rule_id is None
                    and b.predicate_kind
                    in (
                        "missing_upgrade_path",
                        "missing_observation_field",
                    )
                    else None,
                    predicate_kind=b.predicate_kind,
                    severity=b.severity,
                    detail=b.detail,
                )
            )

    return CreateExceptionReviewDraftOutput(
        device_id=body.device_id,
        hostname=hostname,
        candidate_blockers=blockers,
        suggested_expires_at=suggested_expires_at,
        already_active_exception_id=active.id if active is not None else None,
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
