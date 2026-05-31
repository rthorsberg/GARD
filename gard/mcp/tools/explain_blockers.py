"""MCP tool: explain_blockers.

REST parity: ``GET /api/v1/devices/{device_id}/readiness``. Returns the
full ordered ``blockers[]`` plus the recommended-actions for one device.
The AI agent uses this to compose a ticket or runbook body.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.api.schemas.readiness import (
    BlockerModel,
    ReadinessState,
    RecommendedActionModel,
)
from gard.core import readiness_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import Device

TOOL_NAME = "explain_blockers"
REQUIRED_PERMISSION = Permission.READ_READINESS


class ExplainBlockersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID


class ExplainBlockersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str | None = None
    state: ReadinessState
    target_version: str | None = None
    observed_version: str | None = None
    blockers: list[BlockerModel] = Field(default_factory=list)
    recommended_actions: list[RecommendedActionModel] = Field(default_factory=list)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ExplainBlockersInput,
) -> ExplainBlockersOutput:
    device = session.get(Device, body.device_id)
    hostname = device.hostname if device is not None else None

    row = ctrl.latest_evaluation_for(session, body.device_id)
    if row is None:
        return ExplainBlockersOutput(
            device_id=body.device_id,
            hostname=hostname,
            state="not_applicable",
            target_version=None,
            observed_version=None,
            blockers=[],
            recommended_actions=[],
            as_of=dt.datetime.now(dt.UTC),
            correlation_id=get_correlation_id() or "anonymous-correlation",
        )

    return ExplainBlockersOutput(
        device_id=body.device_id,
        hostname=hostname,
        state=row.readiness_state,  # type: ignore[arg-type]
        target_version=row.target_version,
        observed_version=row.observed_version,
        blockers=[BlockerModel(**b) for b in (row.blockers or [])],
        recommended_actions=[
            RecommendedActionModel(**a) for a in (row.recommended_actions or [])
        ],
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
