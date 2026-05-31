"""MCP tool: get_uplift_plan_summary."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import UpliftPlan, UpliftWave

TOOL_NAME = "get_uplift_plan_summary"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class GetUpliftPlanSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: uuid.UUID | None = None


class GetUpliftPlanSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_plans: int = Field(ge=0)
    active_plans: int = Field(ge=0)
    archived_plans: int = Field(ge=0)
    wave_counts_by_state: dict[str, int] = Field(default_factory=dict)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: GetUpliftPlanSummaryInput,
) -> GetUpliftPlanSummaryOutput:
    plan_q = select(UpliftPlan)
    if body.plan_id is not None:
        plan_q = plan_q.where(UpliftPlan.id == body.plan_id)
    plans = list(session.scalars(plan_q))
    total = len(plans)
    archived = sum(1 for p in plans if p.archived_at is not None)
    active = total - archived

    wave_q = select(UpliftWave.state, func.count()).group_by(UpliftWave.state)
    if body.plan_id is not None:
        wave_q = wave_q.where(UpliftWave.plan_id == body.plan_id)
    wave_counts = {state: int(count) for state, count in session.execute(wave_q)}

    return GetUpliftPlanSummaryOutput(
        total_plans=total,
        active_plans=active,
        archived_plans=archived,
        wave_counts_by_state=wave_counts,
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
